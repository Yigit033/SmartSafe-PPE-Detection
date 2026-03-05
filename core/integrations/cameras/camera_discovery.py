"""
SmartSafe AI - IP Camera Discovery System
Real-time network scanning for IP cameras with brand detection
"""

import socket
import threading
import ipaddress
import requests
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

class IPCameraDiscovery:
    """Advanced IP Camera Discovery System"""
    
    def __init__(self):
        self.discovered_cameras = []
        self.scan_progress = 0
        self.total_ips = 0
        
        # Known camera brands and their characteristics
        self.camera_signatures = {
            'hikvision': {
                'ports': [554, 80, 8000, 8080],
                'paths': ['/doc/page/login.asp', '/ISAPI/System/deviceInfo'],
                'headers': ['Server: App-webs/', 'Server: uc-httpd'],
                'default_rtsp': 'rtsp://{ip}:554/Streaming/Channels/101'
            },
            'dahua': {
                'ports': [554, 80, 37777],
                'paths': ['/doc/page/login.asp', '/cgi-bin/magicBox.cgi?action=getDeviceType'],
                'headers': ['Server: DahuaHttp'],
                'default_rtsp': 'rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=0'
            },
            'axis': {
                'ports': [554, 80, 443],
                'paths': ['/axis-cgi/com/ptz.cgi', '/axis-cgi/jpg/image.cgi'],
                'headers': ['Server: axis'],
                'default_rtsp': 'rtsp://{ip}:554/axis-media/media.amp'
            },
            'foscam': {
                'ports': [554, 88, 80],
                'paths': ['/cgi-bin/CGIProxy.fcgi', '/videostream.cgi'],
                'headers': ['Server: Foscam'],
                'default_rtsp': 'rtsp://{ip}:554/videoMain'
            },
            'generic': {
                'ports': [554, 8080, 80],
                'paths': ['/video.cgi', '/videostream.cgi', '/mjpeg'],
                'headers': [],
                'default_rtsp': 'rtsp://{ip}:554/stream'
            }
        }
    
    def scan_network(self, network_range="192.168.1.0/24", timeout=2):
        """Ağı tarar ve IP kameraları bulur.

        Strateji:
        1. ONVIF WS-Discovery (multicast, ~3-4 saniye) — ONVIF destekleyen cihazlar
        2. Paralel port tarama (kalan IP'ler) — ONVIF desteklemeyen cihazlar
        """
        try:
            network = ipaddress.IPv4Network(network_range, strict=False)
            self.total_ips = len(list(network.hosts()))
            self.scan_progress = 0
            self.discovered_cameras = []
            onvif_found_ips = set()

            print(f"🔍 Ağ taranıyor: {network_range} ({self.total_ips} IP)")
            start_time = time.time()

            # ── Phase 1: ONVIF WS-Discovery (fast path) ─────────────────
            try:
                from integrations.cameras.onvif_discovery import get_onvif_manager
                onvif_mgr = get_onvif_manager()
                onvif_devices = onvif_mgr.discover_devices(timeout=min(timeout, 4.0))

                for dev in onvif_devices:
                    ip = dev['ip']
                    onvif_found_ips.add(ip)
                    camera_info = {
                        'ip': ip,
                        'port': 554,  # Standard RTSP port
                        'brand': dev.get('manufacturer', 'ONVIF Device'),
                        'model': dev.get('model', 'IP Camera'),
                        'rtsp_url': f'rtsp://{ip}:554/stream',
                        'resolution': 'Unknown',
                        'status': 'online',
                        'auth_required': True,
                        'detected_ports': [dev.get('port', 80), 554],
                        'discovery_method': 'onvif',
                        'onvif_port': dev.get('port', 80),
                    }
                    self.discovered_cameras.append(camera_info)
                    print(f"📹 ONVIF kamera bulundu: {ip} - {camera_info['brand']}")

                if onvif_devices:
                    print(f"✅ ONVIF keşfi: {len(onvif_devices)} cihaz bulundu")
            except Exception as e:
                print(f"ℹ️ ONVIF keşfi atlandı: {e}")

            # ── Phase 2: Port scan for remaining IPs ─────────────────────
            remaining_hosts = [
                str(ip) for ip in network.hosts()
                if str(ip) not in onvif_found_ips
            ]

            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = {
                    executor.submit(self.scan_ip, ip, timeout): ip
                    for ip in remaining_hosts
                }
                
                for future in as_completed(futures):
                    self.scan_progress += 1
                    ip = futures[future]
                    try:
                        camera_info = future.result()
                        if camera_info:
                            self.discovered_cameras.append(camera_info)
                            print(f"📹 Kamera bulundu: {camera_info['ip']} - {camera_info['brand']}")
                    except Exception as e:
                        pass  # Hata varsa sessizce geç
            
            scan_time = time.time() - start_time
            print(f"✅ Tarama tamamlandı: {len(self.discovered_cameras)} kamera bulundu ({scan_time:.1f}s)")
            
            return {
                'cameras': self.discovered_cameras,
                'scan_time': f"{scan_time:.1f} saniye",
                'total_scanned': self.total_ips,
                'found_count': len(self.discovered_cameras),
                'onvif_count': len(onvif_found_ips),
            }
            
        except Exception as e:
            print(f"❌ Tarama hatası: {str(e)}")
            return {'cameras': [], 'error': str(e)}
    
    def scan_ip(self, ip, timeout=2):
        """Tek bir IP'yi tarar"""
        try:
            # Önce ping kontrolü
            if not self.is_host_alive(ip, timeout):
                return None
            
            # Port taraması ve kamera tespiti
            camera_info = self.detect_camera(ip, timeout)
            return camera_info
            
        except Exception:
            return None
    
    def is_host_alive(self, ip, timeout=1):
        """Host'un aktif olup olmadığını kontrol eder"""
        try:
            # TCP bağlantı testi (HTTP portları)
            for port in [80, 8080, 554]:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((ip, port))
                sock.close()
                if result == 0:
                    return True
            return False
        except:
            return False
    
    def detect_camera(self, ip, timeout=2):
        """IP adresindeki kamerayı tespit eder ve markasını belirler"""
        camera_info = {
            'ip': ip,
            'port': 554,
            'brand': 'Unknown',
            'model': 'IP Camera',
            'rtsp_url': f'rtsp://{ip}:554/stream',
            'resolution': 'Unknown',
            'status': 'online',
            'auth_required': True,
            'detected_ports': []
        }
        
        # Port taraması
        open_ports = self.scan_ports(ip, [80, 554, 8080, 8000, 37777, 88, 443], timeout)
        camera_info['detected_ports'] = open_ports
        
        if not open_ports:
            return None
        
        # Kamera markası tespiti
        brand = self.identify_brand(ip, open_ports, timeout)
        if brand:
            camera_info.update(brand)
            return camera_info
        
        # Generic kamera olarak işaretle
        if 554 in open_ports:
            camera_info['port'] = 554
            camera_info['brand'] = 'Generic'
            camera_info['rtsp_url'] = f'rtsp://{ip}:554/stream'
            return camera_info
        elif 8080 in open_ports:
            camera_info['port'] = 8080
            camera_info['brand'] = 'Generic'
            camera_info['rtsp_url'] = f'rtsp://{ip}:8080/stream'
            return camera_info
        
        return None
    
    def scan_ports(self, ip, ports, timeout=1):
        """Belirtilen portları tarar"""
        open_ports = []
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((ip, port))
                sock.close()
                if result == 0:
                    open_ports.append(port)
            except:
                continue
        return open_ports
    
    def identify_brand(self, ip, open_ports, timeout=2):
        """HTTP istekleri ile kamera markasını tespit eder"""
        for brand, signature in self.camera_signatures.items():
            if brand == 'generic':
                continue
                
            # Port kontrolü
            common_ports = set(signature['ports']) & set(open_ports)
            if not common_ports:
                continue
            
            # HTTP istekleri ile marka tespiti
            for port in common_ports:
                if port in [80, 8080, 8000]:
                    if self.check_http_signature(ip, port, signature, timeout):
                        return {
                            'brand': brand.title(),
                            'model': self.get_camera_model(ip, port, brand, timeout),
                            'port': 554 if 554 in open_ports else port,
                            'rtsp_url': signature['default_rtsp'].format(ip=ip),
                            'resolution': self.detect_resolution(ip, port, timeout),
                            'auth_required': True
                        }
        return None
    
    def check_http_signature(self, ip, port, signature, timeout=2):
        """HTTP yanıtlarında marka imzalarını arar"""
        try:
            # Ana sayfa kontrolü
            response = requests.get(f'http://{ip}:{port}/', timeout=timeout, verify=False)
            headers_str = str(response.headers).lower()
            content = response.text.lower()
            
            # Header kontrolü
            for header in signature['headers']:
                if header.lower() in headers_str:
                    return True
            
            # Path kontrolü
            for path in signature['paths']:
                try:
                    path_response = requests.get(f'http://{ip}:{port}{path}', timeout=1, verify=False)
                    if path_response.status_code in [200, 401, 403]:
                        return True
                except:
                    continue
                    
        except:
            pass
        return False
    
    def get_camera_model(self, ip, port, brand, timeout=2):
        """Kamera modelini tespit etmeye çalışır"""
        try:
            if brand == 'hikvision':
                response = requests.get(f'http://{ip}:{port}/ISAPI/System/deviceInfo', timeout=timeout)
                if 'model' in response.text.lower():
                    return 'DS-2CD Series'
            elif brand == 'dahua':
                return 'IPC Series'
            elif brand == 'axis':
                return 'AXIS Camera'
            elif brand == 'foscam':
                return 'Foscam Camera'
        except:
            pass
        return 'IP Camera'
    
    def detect_resolution(self, ip, port, timeout=1):
        """Kamera çözünürlüğünü tespit etmeye çalışır"""
        try:
            # Basit çözünürlük tespiti
            response = requests.get(f'http://{ip}:{port}/', timeout=timeout)
            content = response.text.lower()
            
            if '4k' in content or '3840' in content:
                return '4K'
            elif '1080p' in content or '1920' in content:
                return '1080p'
            elif '720p' in content or '1280' in content:
                return '720p'
            else:
                return '2MP'  # Default assumption
        except:
            return '2MP'
    
    def test_camera_connection(self, camera_config):
        """Kamera bağlantısını test eder"""
        results = {
            'connection_status': 'failed',
            'response_time': 'N/A',
            'resolution': 'Unknown',
            'fps': 0,
            'codec': 'Unknown',
            'bitrate': 'Unknown',
            'ptz_support': False,
            'night_vision': False,
            'audio_support': False,
            'test_duration': '0s',
            'quality_score': 0
        }
        
        start_time = time.time()
        
        try:
            ip = camera_config.get('ip')
            port = camera_config.get('port', 554)
            
            # 1. Ping testi
            ping_start = time.time()
            if self.is_host_alive(ip, 1):
                ping_time = (time.time() - ping_start) * 1000
                results['response_time'] = f'{ping_time:.0f}ms'
                results['connection_status'] = 'success'
            else:
                return results
            
            # 2. Port erişilebilirlik
            open_ports = self.scan_ports(ip, [port, 80, 8080], 2)
            if not open_ports:
                results['connection_status'] = 'failed'
                return results
            
            # 3. HTTP bilgi toplama
            if 80 in open_ports or 8080 in open_ports:
                http_port = 80 if 80 in open_ports else 8080
                try:
                    response = requests.get(f'http://{ip}:{http_port}/', timeout=3)
                    content = response.text.lower()
                    
                    # Çözünürlük tespiti
                    results['resolution'] = self.detect_resolution(ip, http_port, 2)
                    
                    # Özellik tespiti
                    if 'ptz' in content:
                        results['ptz_support'] = True
                    if 'night' in content or 'ir' in content:
                        results['night_vision'] = True
                    if 'audio' in content or 'sound' in content:
                        results['audio_support'] = True
                    
                    # FPS ve codec tahmini
                    results['fps'] = 25  # Default
                    results['codec'] = 'H.264'  # Most common
                    results['bitrate'] = '2048 kbps'  # Reasonable default
                    
                except:
                    pass
            
            # 4. RTSP bağlantı testi (basit)
            try:
                rtsp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                rtsp_socket.settimeout(3)
                rtsp_result = rtsp_socket.connect_ex((ip, port))
                rtsp_socket.close()
                
                if rtsp_result == 0:
                    results['quality_score'] = 8.5
                else:
                    results['quality_score'] = 6.0
            except:
                results['quality_score'] = 5.0
            
            test_duration = time.time() - start_time
            results['test_duration'] = f'{test_duration:.1f} saniye'
            
        except Exception as e:
            results['connection_status'] = 'failed'
            results['error'] = str(e)
        
        return results

# Test fonksiyonu
def test_discovery():
    """Keşif sistemini test eder"""
    print("🚀 SmartSafe AI - IP Camera Discovery Test")
    print("=" * 50)
    
    discovery = IPCameraDiscovery()
    
    # Ağ taraması
    result = discovery.scan_network("192.168.1.0/24", timeout=1)
    
    print(f"\n📊 Sonuçlar:")
    print(f"  - Taranan IP: {result.get('total_scanned', 0)}")
    print(f"  - Bulunan Kamera: {result.get('found_count', 0)}")
    print(f"  - Tarama Süresi: {result.get('scan_time', 'Unknown')}")
    
    # Bulunan kameraları listele
    if result['cameras']:
        print(f"\n📹 Bulunan Kameralar:")
        for camera in result['cameras']:
            print(f"  - {camera['ip']}:{camera['port']} - {camera['brand']} {camera['model']}")
            print(f"    RTSP: {camera['rtsp_url']}")
    
    return result

if __name__ == "__main__":
    test_discovery() 