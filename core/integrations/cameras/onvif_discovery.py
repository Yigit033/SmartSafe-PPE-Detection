#!/usr/bin/env python3
"""
SmartSafe AI — ONVIF Camera Discovery & Integration Module
Enterprise-grade ONVIF protocol support for automated camera discovery,
stream URI retrieval, and NVR channel enumeration.

Uses WS-Discovery for zero-config camera finding and ONVIF device management
for reliable RTSP URI retrieval — no more URL guessing.

Dependencies: pip install onvif-zeep-async  (or onvif-zeep)
Fallback:     Works gracefully without the library — returns empty results.
"""

import logging
import socket
import threading
import time
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ── Lazy import: onvif-zeep ─────────────────────────────────────────────────
# We wrap in a helper so the rest of the app doesn't crash if the package
# isn't installed yet.
_onvif_available = None  # tri-state: None = not checked, True/False


def _ensure_onvif():
    """Try to import onvif; cache result."""
    global _onvif_available
    if _onvif_available is not None:
        return _onvif_available
    try:
        from onvif import ONVIFCamera  # noqa: F401
        _onvif_available = True
        logger.info("✅ ONVIF kütüphanesi mevcut (onvif-zeep)")
    except ImportError:
        _onvif_available = False
        logger.warning(
            "⚠️ onvif-zeep yüklü değil. ONVIF keşfi devre dışı. "
            "Kurmak için: pip install onvif-zeep-async"
        )
    return _onvif_available


# ── WS-Discovery (ONVIF cihazlarını ağda bul) ──────────────────────────────

def _ws_discovery_probe(timeout: float = 3.0) -> List[Dict[str, str]]:
    """
    Send a WS-Discovery Probe multicast and collect ONVIF device responses.

    Returns a list of dicts with keys: 'ip', 'port', 'xaddrs', 'scopes'.
    Works without any third-party library — pure UDP socket.
    """
    MULTICAST_ADDR = "239.255.255.250"
    MULTICAST_PORT = 3702

    # SOAP WS-Discovery Probe message targeting ONVIF devices
    probe_msg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
        ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
        ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        '<e:Header>'
        '<w:MessageID>uuid:smartsafe-discovery-probe</w:MessageID>'
        '<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
        '</e:Header>'
        '<e:Body>'
        '<d:Probe>'
        '<d:Types>dn:NetworkVideoTransmitter</d:Types>'
        '</d:Probe>'
        '</e:Body>'
        '</e:Envelope>'
    )

    discovered: List[Dict[str, str]] = []
    seen_ips: set = set()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        # Allow multicast on any interface
        sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4
        )

        sock.sendto(probe_msg.encode("utf-8"), (MULTICAST_ADDR, MULTICAST_PORT))
        logger.info("📡 WS-Discovery Probe gönderildi, yanıt bekleniyor...")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)

                # Parse minimal fields from response XML
                response_text = data.decode("utf-8", errors="replace")
                xaddrs = _extract_xml_value(response_text, "XAddrs")
                scopes = _extract_xml_value(response_text, "Scopes")

                # Extract ONVIF port from XAddrs if available
                port = 80
                if xaddrs:
                    try:
                        from urllib.parse import urlparse
                        parsed = urlparse(xaddrs.split()[0])
                        port = parsed.port or 80
                    except Exception:
                        pass

                discovered.append({
                    'ip': ip,
                    'port': port,
                    'xaddrs': xaddrs or '',
                    'scopes': scopes or '',
                })
                logger.info(f"✅ WS-Discovery yanıt: {ip}:{port}")
            except socket.timeout:
                break
            except Exception as e:
                logger.debug(f"WS-Discovery parse hatası: {e}")
                continue
    except Exception as e:
        logger.warning(f"⚠️ WS-Discovery Probe başarısız: {e}")
    finally:
        try:
            sock.close()
        except Exception:
            pass

    return discovered


def _extract_xml_value(xml_text: str, tag_local: str) -> Optional[str]:
    """Extract value of a tag by local name (ignoring namespace prefix)."""
    import re
    # Matches <ns:TagName>value</ns:TagName> or <TagName>value</TagName>
    pattern = rf"<[^>]*?{tag_local}[^>]*?>(.*?)</[^>]*?{tag_local}>"
    match = re.search(pattern, xml_text, re.DOTALL)
    return match.group(1).strip() if match else None


# ── ONVIFDeviceManager ──────────────────────────────────────────────────────

class ONVIFDeviceManager:
    """
    Enterprise-grade ONVIF device manager.

    Capabilities:
    - WS-Discovery: Zero-config multicast device finding
    - Device info: Manufacturer, model, firmware, serial number
    - Media profiles: Resolution, codec, framerate per profile
    - Stream URI: Get the exact RTSP URL from the device (no guessing)
    - NVR channel enumeration: List all channels on NVR/DVR via ONVIF
    - Snapshot URI: For quick previews without opening RTSP
    """

    def __init__(self, default_username: str = "admin",
                 default_password: str = "admin",
                 connect_timeout: int = 5):
        self.default_username = default_username
        self.default_password = default_password
        self.connect_timeout = connect_timeout
        # Cache: ip -> ONVIFCamera instance
        self._device_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    # ── Discovery ───────────────────────────────────────────────────────

    def discover_devices(self, timeout: float = 4.0,
                         network_range: Optional[str] = None) -> List[Dict]:
        """
        Discover ONVIF devices on the local network.

        Uses WS-Discovery multicast first (fast, standard).
        Then optionally probes a network range for port 80/8899 as fallback.

        Returns list of dicts: {ip, port, manufacturer, model, is_onvif}
        """
        results: List[Dict] = []
        seen_ips: set = set()

        # --- Phase 1: WS-Discovery (multicast, ~3-4 seconds) ---
        ws_devices = _ws_discovery_probe(timeout=timeout)
        for dev in ws_devices:
            ip = dev['ip']
            seen_ips.add(ip)
            info = {
                'ip': ip,
                'port': dev['port'],
                'is_onvif': True,
                'discovery_method': 'ws-discovery',
                'manufacturer': 'Unknown',
                'model': 'Unknown',
                'scopes': dev.get('scopes', ''),
            }
            # Try to extract brand from scopes
            scopes = dev.get('scopes', '').lower()
            if 'hikvision' in scopes:
                info['manufacturer'] = 'Hikvision'
            elif 'dahua' in scopes:
                info['manufacturer'] = 'Dahua'
            elif 'axis' in scopes:
                info['manufacturer'] = 'Axis'
            elif 'hanwha' in scopes or 'samsung' in scopes:
                info['manufacturer'] = 'Hanwha (Samsung)'
            elif 'bosch' in scopes:
                info['manufacturer'] = 'Bosch'
            elif 'uniview' in scopes:
                info['manufacturer'] = 'Uniview'
            results.append(info)

        # --- Phase 2: Network range probe (fallback for devices with multicast disabled) ---
        if network_range:
            try:
                import ipaddress
                network = ipaddress.ip_network(network_range, strict=False)
                probe_ips = [str(ip) for ip in network.hosts() if str(ip) not in seen_ips]

                # Probe common ONVIF ports in parallel
                with ThreadPoolExecutor(max_workers=32) as executor:
                    futures = {}
                    for ip in probe_ips:
                        for port in [80, 8899, 8080]:
                            futures[executor.submit(
                                self._probe_onvif_port, ip, port
                            )] = (ip, port)

                    for future in as_completed(futures, timeout=timeout + 2):
                        ip, port = futures[future]
                        try:
                            is_onvif = future.result()
                            if is_onvif and ip not in seen_ips:
                                seen_ips.add(ip)
                                results.append({
                                    'ip': ip,
                                    'port': port,
                                    'is_onvif': True,
                                    'discovery_method': 'port-probe',
                                    'manufacturer': 'Unknown',
                                    'model': 'Unknown',
                                })
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"⚠️ Network range probe hatası: {e}")

        logger.info(f"📡 ONVIF keşfi tamamlandı: {len(results)} cihaz bulundu")
        return results

    def _probe_onvif_port(self, ip: str, port: int) -> bool:
        """Check if an IP:port responds to ONVIF GetSystemDateAndTime."""
        try:
            import requests
            soap_body = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
                ' xmlns:tds="http://www.onvif.org/ver10/device/wsdl">'
                '<s:Body><tds:GetSystemDateAndTime/></s:Body>'
                '</s:Envelope>'
            )
            url = f"http://{ip}:{port}/onvif/device_service"
            resp = requests.post(
                url, data=soap_body, timeout=1.5,
                headers={"Content-Type": "application/soap+xml; charset=utf-8"}
            )
            return resp.status_code == 200 and "SystemDateAndTime" in resp.text
        except Exception:
            return False

    # ── Device Info ─────────────────────────────────────────────────────

    def get_device_info(self, ip: str, port: int = 80,
                        username: str = None, password: str = None) -> Dict:
        """
        Get detailed device information via ONVIF.

        Returns: {manufacturer, model, firmware_version, serial_number,
                  hardware_id, is_onvif, profiles_count}
        """
        username = username or self.default_username
        password = password or self.default_password

        if not _ensure_onvif():
            return self._fallback_device_info(ip, port, username, password)

        try:
            from onvif import ONVIFCamera
            camera = ONVIFCamera(ip, port, username, password,
                                 no_cache=True)

            device_info = camera.devicemgmt.GetDeviceInformation()

            # Get profile count
            media_service = camera.create_media_service()
            profiles = media_service.GetProfiles()

            result = {
                'ip': ip,
                'port': port,
                'is_onvif': True,
                'manufacturer': getattr(device_info, 'Manufacturer', 'Unknown'),
                'model': getattr(device_info, 'Model', 'Unknown'),
                'firmware_version': getattr(device_info, 'FirmwareVersion', 'Unknown'),
                'serial_number': getattr(device_info, 'SerialNumber', 'Unknown'),
                'hardware_id': getattr(device_info, 'HardwareId', 'Unknown'),
                'profiles_count': len(profiles) if profiles else 0,
            }

            # Cache the camera instance for reuse
            with self._cache_lock:
                self._device_cache[ip] = camera

            logger.info(
                f"✅ ONVIF cihaz bilgisi: {result['manufacturer']} {result['model']} "
                f"@ {ip}:{port} ({result['profiles_count']} profil)"
            )
            return result

        except Exception as e:
            logger.warning(f"⚠️ ONVIF cihaz bilgisi alınamadı ({ip}:{port}): {e}")
            return self._fallback_device_info(ip, port, username, password)

    def _fallback_device_info(self, ip: str, port: int,
                              username: str, password: str) -> Dict:
        """Fallback: try HTTP headers/signature to detect brand."""
        result = {
            'ip': ip,
            'port': port,
            'is_onvif': False,
            'manufacturer': 'Unknown',
            'model': 'Unknown',
            'firmware_version': 'Unknown',
            'serial_number': 'Unknown',
            'hardware_id': 'Unknown',
            'profiles_count': 0,
        }
        try:
            import requests
            for p in [port, 80, 8080]:
                try:
                    resp = requests.get(
                        f"http://{ip}:{p}/", timeout=2,
                        auth=(username, password)
                    )
                    server = resp.headers.get('Server', '').lower()
                    body = resp.text.lower()[:2000]
                    if 'hikvision' in server or 'hikvision' in body:
                        result['manufacturer'] = 'Hikvision'
                    elif 'dahua' in server or 'dahua' in body:
                        result['manufacturer'] = 'Dahua'
                    elif 'axis' in server:
                        result['manufacturer'] = 'Axis'
                    if result['manufacturer'] != 'Unknown':
                        break
                except Exception:
                    continue
        except Exception:
            pass
        return result

    # ── Media Profiles ──────────────────────────────────────────────────

    def get_profiles(self, ip: str, port: int = 80,
                     username: str = None, password: str = None) -> List[Dict]:
        """
        Get media profiles from ONVIF device.

        Each profile includes: {name, token, resolution, codec, fps}
        """
        username = username or self.default_username
        password = password or self.default_password

        if not _ensure_onvif():
            return []

        try:
            camera = self._get_or_create_camera(ip, port, username, password)
            media_service = camera.create_media_service()
            profiles = media_service.GetProfiles()

            result = []
            for profile in profiles:
                profile_info = {
                    'name': getattr(profile, 'Name', 'Unknown'),
                    'token': getattr(profile, 'token', ''),
                }

                # Extract video encoder config
                vec = getattr(profile, 'VideoEncoderConfiguration', None)
                if vec:
                    resolution = getattr(vec, 'Resolution', None)
                    profile_info['width'] = getattr(resolution, 'Width', 0) if resolution else 0
                    profile_info['height'] = getattr(resolution, 'Height', 0) if resolution else 0
                    profile_info['codec'] = getattr(vec, 'Encoding', 'H264')
                    rate_control = getattr(vec, 'RateControl', None)
                    profile_info['fps'] = getattr(rate_control, 'FrameRateLimit', 25) if rate_control else 25
                    profile_info['bitrate'] = getattr(rate_control, 'BitrateLimit', 0) if rate_control else 0
                else:
                    profile_info.update({'width': 0, 'height': 0, 'codec': 'Unknown', 'fps': 25, 'bitrate': 0})

                result.append(profile_info)

            logger.info(f"✅ ONVIF profiller: {ip} — {len(result)} profil bulundu")
            return result

        except Exception as e:
            logger.warning(f"⚠️ ONVIF profil alınamadı ({ip}): {e}")
            return []

    # ── Stream URI ──────────────────────────────────────────────────────

    def get_stream_uri(self, ip: str, port: int = 80,
                       username: str = None, password: str = None,
                       profile_index: int = 0,
                       protocol: str = 'RTSP') -> Optional[str]:
        """
        Get the exact RTSP stream URI from the device via ONVIF.

        This replaces all URL guessing — the device tells us the correct URI.

        Args:
            ip: Device IP
            port: ONVIF port (usually 80)
            username/password: Credentials
            profile_index: Which media profile to use (0 = main stream, 1 = sub)
            protocol: 'RTSP' or 'HTTP'

        Returns:
            RTSP URI string, or None on failure
        """
        username = username or self.default_username
        password = password or self.default_password

        if not _ensure_onvif():
            return None

        try:
            camera = self._get_or_create_camera(ip, port, username, password)
            media_service = camera.create_media_service()
            profiles = media_service.GetProfiles()

            if not profiles or profile_index >= len(profiles):
                logger.warning(f"⚠️ ONVIF profil {profile_index} bulunamadı, {len(profiles)} profil mevcut")
                return None

            profile_token = profiles[profile_index].token

            # Build the request for GetStreamUri
            stream_setup = media_service.create_type('GetStreamUri')
            stream_setup.ProfileToken = profile_token
            stream_setup.StreamSetup = {
                'Stream': 'RTP-Unicast',
                'Transport': {'Protocol': protocol}
            }

            uri_response = media_service.GetStreamUri(stream_setup)
            raw_uri = getattr(uri_response, 'Uri', None)

            if not raw_uri:
                logger.warning(f"⚠️ ONVIF stream URI boş döndü ({ip})")
                return None

            # Inject credentials into URI if not present
            from urllib.parse import urlparse, urlunparse, quote
            parsed = urlparse(raw_uri)
            if not parsed.username:
                safe_user = quote(username, safe='')
                safe_pass = quote(password, safe='')
                netloc = f"{safe_user}:{safe_pass}@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                raw_uri = urlunparse(parsed._replace(netloc=netloc))

            logger.info(f"✅ ONVIF stream URI alındı: {ip} profil[{profile_index}]")
            return raw_uri

        except Exception as e:
            logger.warning(f"⚠️ ONVIF stream URI alınamadı ({ip}): {e}")
            return None

    # ── Snapshot URI ────────────────────────────────────────────────────

    def get_snapshot_uri(self, ip: str, port: int = 80,
                         username: str = None, password: str = None,
                         profile_index: int = 0) -> Optional[str]:
        """Get snapshot (still image) URI from ONVIF device."""
        username = username or self.default_username
        password = password or self.default_password

        if not _ensure_onvif():
            return None

        try:
            camera = self._get_or_create_camera(ip, port, username, password)
            media_service = camera.create_media_service()
            profiles = media_service.GetProfiles()

            if not profiles or profile_index >= len(profiles):
                return None

            profile_token = profiles[profile_index].token
            snapshot_uri = media_service.GetSnapshotUri({'ProfileToken': profile_token})
            uri = getattr(snapshot_uri, 'Uri', None)

            if uri:
                logger.info(f"✅ ONVIF snapshot URI: {ip}")
            return uri

        except Exception as e:
            logger.debug(f"ONVIF snapshot URI alınamadı ({ip}): {e}")
            return None

    # ── NVR Channel Enumeration ─────────────────────────────────────────

    def enumerate_channels(self, ip: str, port: int = 80,
                           username: str = None, password: str = None) -> List[Dict]:
        """
        Enumerate all video channels on an NVR/DVR via ONVIF.

        For an NVR, each connected camera appears as a separate media profile
        or video source. This method returns all of them.

        Returns list of: {channel_number, name, token, resolution, stream_uri}
        """
        username = username or self.default_username
        password = password or self.default_password

        channels: List[Dict] = []

        if not _ensure_onvif():
            return channels

        try:
            camera = self._get_or_create_camera(ip, port, username, password)
            media_service = camera.create_media_service()

            # Get all profiles — on an NVR each profile ≈ one channel
            profiles = media_service.GetProfiles()
            if not profiles:
                logger.warning(f"⚠️ ONVIF: {ip} üzerinde profil bulunamadı")
                return channels

            for idx, profile in enumerate(profiles):
                channel_info = {
                    'channel_number': idx + 1,
                    'name': getattr(profile, 'Name', f'Channel {idx + 1}'),
                    'token': getattr(profile, 'token', ''),
                    'width': 0,
                    'height': 0,
                    'codec': 'Unknown',
                    'stream_uri': None,
                }

                # Resolution info
                vec = getattr(profile, 'VideoEncoderConfiguration', None)
                if vec:
                    res = getattr(vec, 'Resolution', None)
                    if res:
                        channel_info['width'] = getattr(res, 'Width', 0)
                        channel_info['height'] = getattr(res, 'Height', 0)
                    channel_info['codec'] = getattr(vec, 'Encoding', 'H264')

                # Get stream URI for this channel
                try:
                    stream_setup = media_service.create_type('GetStreamUri')
                    stream_setup.ProfileToken = profile.token
                    stream_setup.StreamSetup = {
                        'Stream': 'RTP-Unicast',
                        'Transport': {'Protocol': 'RTSP'}
                    }
                    uri_resp = media_service.GetStreamUri(stream_setup)
                    raw_uri = getattr(uri_resp, 'Uri', None)

                    if raw_uri:
                        # Inject credentials
                        from urllib.parse import urlparse, urlunparse, quote
                        parsed = urlparse(raw_uri)
                        if not parsed.username:
                            safe_user = quote(username, safe='')
                            safe_pass = quote(password, safe='')
                            netloc = f"{safe_user}:{safe_pass}@{parsed.hostname}"
                            if parsed.port:
                                netloc += f":{parsed.port}"
                            raw_uri = urlunparse(parsed._replace(netloc=netloc))
                        channel_info['stream_uri'] = raw_uri
                except Exception as uri_err:
                    logger.debug(f"ONVIF kanal {idx+1} URI alınamadı: {uri_err}")

                channels.append(channel_info)

            logger.info(f"✅ ONVIF kanal listesi: {ip} — {len(channels)} kanal")

        except Exception as e:
            logger.warning(f"⚠️ ONVIF kanal listesi alınamadı ({ip}): {e}")

        return channels

    # ── ONVIF Connection Test ───────────────────────────────────────────

    def test_connection(self, ip: str, port: int = 80,
                        username: str = None, password: str = None) -> Dict:
        """
        Test ONVIF connection to a device.

        Returns: {success, is_onvif, device_info, profiles_count, error}
        """
        username = username or self.default_username
        password = password or self.default_password

        result = {
            'success': False,
            'is_onvif': False,
            'ip': ip,
            'port': port,
            'device_info': {},
            'profiles_count': 0,
            'channels_count': 0,
            'error': None,
        }

        # Step 1: Check basic TCP connectivity
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.connect_timeout)
            conn_result = sock.connect_ex((ip, port))
            sock.close()
            if conn_result != 0:
                result['error'] = f"TCP bağlantı başarısız (port {port})"
                return result
        except Exception as e:
            result['error'] = f"Ağ hatası: {e}"
            return result

        # Step 2: Get device info
        device_info = self.get_device_info(ip, port, username, password)
        result['device_info'] = device_info
        result['is_onvif'] = device_info.get('is_onvif', False)
        result['profiles_count'] = device_info.get('profiles_count', 0)

        if result['is_onvif']:
            # Step 3: Enumerate channels
            channels = self.enumerate_channels(ip, port, username, password)
            result['channels_count'] = len(channels)
            result['success'] = True
            logger.info(
                f"✅ ONVIF bağlantı testi başarılı: {ip}:{port} — "
                f"{result['profiles_count']} profil, {result['channels_count']} kanal"
            )
        else:
            result['error'] = "Cihaz ONVIF desteklemiyor veya kimlik bilgileri hatalı"

        return result

    # ── Internal Helpers ────────────────────────────────────────────────

    def _get_or_create_camera(self, ip: str, port: int,
                              username: str, password: str):
        """Get cached ONVIFCamera instance or create a new one."""
        cache_key = f"{ip}:{port}"
        with self._cache_lock:
            if cache_key in self._device_cache:
                return self._device_cache[cache_key]

        from onvif import ONVIFCamera
        camera = ONVIFCamera(ip, port, username, password, no_cache=True)
        with self._cache_lock:
            self._device_cache[cache_key] = camera
        return camera

    def clear_cache(self):
        """Clear the device cache."""
        with self._cache_lock:
            self._device_cache.clear()
        logger.info("✅ ONVIF cihaz cache temizlendi")


# ── Module-level singleton ──────────────────────────────────────────────────
_onvif_manager: Optional[ONVIFDeviceManager] = None
_manager_lock = threading.Lock()


def get_onvif_manager() -> ONVIFDeviceManager:
    """Get or create the global ONVIFDeviceManager singleton."""
    global _onvif_manager
    if _onvif_manager is None:
        with _manager_lock:
            if _onvif_manager is None:
                _onvif_manager = ONVIFDeviceManager()
    return _onvif_manager
