#!/usr/bin/env python3
"""
DVR Stream Handler - Multi-Brand RTSP to Browser Video Conversion
Supports Hikvision, Dahua, Axis, and other DVR/NVR systems
"""

import cv2
import numpy as np
import threading
import time
import base64
import socket
import re
import os
from typing import Dict, Optional, List, Tuple
import logging
import urllib.parse

from utils.redaction import redact_url

logger = logging.getLogger(__name__)

class DVRStreamHandler:
    """Advanced DVR stream handler with multi-brand support"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.active_streams: Dict[str, Dict] = {}
        self.frame_buffers: Dict[str, list] = {}
        self.max_buffer_size = 5  # Reduced from 10 to 5 for smoother playback
        self.connection_timeout = 3000  # Reduced from 5000 to 3000 ms for faster connection
        self.read_timeout = 2000  # Reduced from 3000 to 2000 ms for faster frame reading

        # ══════════════════════════════════════════════════════════════════
        # 🛡️ RTSP over TCP — UDP paket kaybını önler, H.265 PPS hatalarını bitirir
        # FFmpeg'in varsayılan UDP yerine TCP kullanmasını zorlar.
        # Bu, özellikle Hikvision/Dahua NVR'larda "PPS id out of range" hatasını çözer.
        # ══════════════════════════════════════════════════════════════════
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;2000000|probesize;1000000"
        logger.info("🛡️ RTSP over TCP enforced globally via OPENCV_FFMPEG_CAPTURE_OPTIONS")

        # Singleton model instance'ları — her detection çağrısında yeniden oluşturulmaz
        # Bu, çok kanallı DVR'da RAM/GPU patlamasnı önler.
        self._sh17_manager = None   # Lazy init at first use
        self._pose_detector = None  # Lazy init at first use

        # ONVIF URI cache — cihazdan alınan kesin URI'ler saklanır (tahmine gerek kalmaz)
        self._onvif_uri_cache: Dict[str, str] = {}

        # ══════════════════════════════════════════════════════════════════
        # ⚡ Success URL Cache — Bulunan çalışan RTSP URL'leri bellekte saklanır
        # İlk bağlantı: Discovery (26 URL taraması) → sonraki bağlantı: <500ms
        # Key format: "ip:channel" → Value: çalışan tam RTSP URL
        # ══════════════════════════════════════════════════════════════════
        self._success_url_cache: Dict[str, str] = {}

        # ══════════════════════════════════════════════════════════════════
        # 🌩️ Probe storm controls
        # - Concurrency limit: prevents dozens of simultaneous RTSP opens
        # - TTL caches: avoid repeating expensive discovery/probes
        # - Retry budgets: cap URL attempts per operation
        # ══════════════════════════════════════════════════════════════════
        try:
            probe_conc = int(os.getenv("DVR_PROBE_CONCURRENCY", "4"))
        except Exception:
            probe_conc = 4
        self._probe_sem = threading.Semaphore(max(1, probe_conc))

        try:
            self._probe_ttl_success_s = int(os.getenv("DVR_PROBE_TTL_SUCCESS_S", "600"))
        except Exception:
            self._probe_ttl_success_s = 600
        try:
            self._probe_ttl_fail_s = int(os.getenv("DVR_PROBE_TTL_FAIL_S", "60"))
        except Exception:
            self._probe_ttl_fail_s = 60

        # key -> (value, expires_at)
        self._probe_success_ttl: Dict[str, Tuple[str, float]] = {}
        self._probe_fail_ttl: Dict[str, Tuple[str, float]] = {}

        try:
            self._start_url_budget = int(os.getenv("DVR_START_URL_BUDGET", "18"))
        except Exception:
            self._start_url_budget = 18
        try:
            self._probe_url_budget = int(os.getenv("DVR_CHANNEL_PROBE_URL_BUDGET", "6"))
        except Exception:
            self._probe_url_budget = 6
        try:
            self._channel_probe_workers = int(os.getenv("DVR_CHANNEL_PROBE_WORKERS", "4"))
        except Exception:
            self._channel_probe_workers = 4

        # DVR brand-specific URL patterns
        self.dvr_url_patterns = {
            'hikvision': [
                '/ch{channel:02d}/main',
                '/ch{channel:02d}/sub',
                '/ch{channel:02d}/0',
                '/ch{channel:02d}/1',
                '/cam/realmonitor?channel={channel}&subtype=0',
                '/cam/realmonitor?channel={channel}&subtype=1',
                '/cam/realmonitor?channel={channel}&subtype=2',
                '/ISAPI/Streaming/channels/{channel}01',
                '/ISAPI/Streaming/channels/{channel}02',
                '/ISAPI/Streaming/channels/{channel}03',
                '/live/ch{channel:02d}',
                '/live/channel{channel}',
                '/live/camera{channel}',
                '/cam/realmonitor?channel={channel}&subtype=0&authbasic=1',
                '/cam/realmonitor?channel={channel}&subtype=1&authbasic=1'
            ],
            # XM/Xiongmai family (and compatibles) often require credentials in query string
            'xm': [
                '/user={username}&password={password}&channel={channel}&stream=0.sdp',  # main stream
                '/user={username}&password={password}&channel={channel}&stream=1.sdp',  # sub stream
                '/live/{channel}.sdp',
                '/h264/{channel}/main/av_stream'
            ],
            'dahua': [
                '/cam/realmonitor?channel={channel}&subtype=0',
                '/cam/realmonitor?channel={channel}&subtype=1',
                '/cam/realmonitor?channel={channel}&subtype=2',
                '/cam/realmonitor?channel={channel}&subtype=0&authbasic=1',
                '/cam/realmonitor?channel={channel}&subtype=1&authbasic=1',
                '/ch{channel:02d}/main',
                '/ch{channel:02d}/sub',
                '/ch{channel:02d}/0',
                '/ch{channel:02d}/1',
                '/ch{channel:02d}/main/0',
                '/ch{channel:02d}/main/1',
                '/live/ch{channel:02d}',
                '/live/channel{channel}',
                '/live/camera{channel}',
                '/cam/realmonitor?channel={channel}&subtype=0&stream=0',
                '/cam/realmonitor?channel={channel}&subtype=1&stream=1'
            ],
            'axis': [
                '/axis-media/media.amp?videocodec=h264&camera={channel}',
                '/axis-media/media.amp?videocodec=mjpeg&camera={channel}',
                '/axis-media/media.amp?camera={channel}',
                '/axis-media/media.amp?videocodec=h264&camera={channel}&resolution=1920x1080',
                '/axis-media/media.amp?videocodec=mjpeg&camera={channel}&resolution=1280x720'
            ],
            'generic': [
                '/ch{channel:02d}/main',
                '/ch{channel:02d}/sub',
                '/ch{channel:02d}/0',
                '/ch{channel:02d}/1',
                '/ch{channel:02d}/main/0',
                '/ch{channel:02d}/main/1',
                '/ch{channel:02d}/sub/0',
                '/ch{channel:02d}/sub/1',
                '/cam/realmonitor?channel={channel}&subtype=0',
                '/cam/realmonitor?channel={channel}&subtype=1',
                '/cam/realmonitor?channel={channel}&subtype=2',
                '/live/ch{channel:02d}',
                '/live/channel{channel}',
                '/live/camera{channel}',
                '/live/ch{channel:02d}/main',
                '/live/ch{channel:02d}/sub',
                '/live/channel{channel}/main',
                '/live/channel{channel}/sub',
                '/live/camera{channel}/main',
                '/live/camera{channel}/sub',
                '/stream/ch{channel:02d}',
                '/stream/channel{channel}',
                '/stream/camera{channel}',
                '/video/ch{channel:02d}',
                '/video/channel{channel}',
                '/video/camera{channel}'
            ]
        }

    def _ttl_get(self, d: Dict[str, Tuple[str, float]], key: str) -> Optional[str]:
        v = d.get(key)
        if not v:
            return None
        value, exp = v
        if time.time() >= exp:
            d.pop(key, None)
            return None
        return value

    def _ttl_set(self, d: Dict[str, Tuple[str, float]], key: str, value: str, ttl_s: int):
        d[key] = (value, time.time() + max(1, ttl_s))

    # ─────────────────────────────────────────────────────────────────────
    # State machine helpers
    # ─────────────────────────────────────────────────────────────────────
    def _transition(
        self,
        stream_id: str,
        new_status: str,
        *,
        reason: Optional[str] = None,
        error_code: Optional[str] = None,
    ):
        now = time.time()
        with self._lock:
            if stream_id not in self.active_streams:
                self.active_streams[stream_id] = {}
            st = self.active_streams[stream_id]
            st["status"] = new_status
            st["last_transition_ts"] = now
            if reason is not None:
                st["status_reason"] = reason
            if error_code is not None:
                st["last_error_code"] = error_code

    def _ensure_stream_config(
        self,
        stream_id: str,
        *,
        company_id: Optional[str],
        sector: Optional[str],
        required_ppe: Optional[list],
    ):
        """Resolve and freeze (immutable) detection config for this stream."""
        if not company_id and (sector or required_ppe):
            cfg = {"sector": sector, "required_ppe": required_ppe}
        else:
            cfg = {}
            if company_id:
                try:
                    from database.database_adapter import DatabaseAdapter
                    db = DatabaseAdapter()
                    cfg = db.get_company_detection_config(company_id) or {}
                except Exception:
                    cfg = {}
            if sector and not cfg.get("sector"):
                cfg["sector"] = sector
            if required_ppe is not None and cfg.get("required_ppe") is None:
                cfg["required_ppe"] = required_ppe

        # Freeze into stream metadata
        with self._lock:
            st = self.active_streams.get(stream_id, {})
            if "immutable_config" not in st:
                st["immutable_config"] = {
                    "company_id": company_id,
                    "sector": cfg.get("sector") or None,
                    "required_ppe": cfg.get("required_ppe"),
                }
                # Also keep top-level sector for backwards-compat
                if cfg.get("sector"):
                    st["sector"] = cfg.get("sector")
            self.active_streams[stream_id] = st

    def detect_dvr_brand(self, ip_address: str, username: str, password: str, rtsp_port: int) -> str:
        """Detect DVR brand by testing common URL patterns"""
        try:
            # Test multiple channels for brand detection
            safe_username = urllib.parse.quote(username)
            safe_password = urllib.parse.quote(password)

            test_channels = [1, 2]  # Kanal 1 ve 2 yeterli — çoğu DVR'da bu kanallar aktif
            test_urls = []

            for channel in test_channels:
                test_urls.extend([
                    f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{channel}01",
                    f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel}&subtype=0",
                    f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel:02d}/main",
                    f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel:02d}/sub",
                    # XM-style credential-in-query
                    f"rtsp://{ip_address}:{rtsp_port}/user={safe_username}&password={safe_password}&channel={channel}&stream=0.sdp",
                ])
            
            for url in test_urls:
                cap = None
                try:
                    cap = cv2.VideoCapture(url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
                    if cap.isOpened():
                        cap.release()
                        cap = None
                        if 'stream=0.sdp' in url and '/user=' in url:
                            logger.info(f"✅ Detected XM DVR via URL: {url}")
                            return 'xm'
                        if 'ISAPI' in url:
                            logger.info(f"✅ Detected Hikvision DVR via URL: {url}")
                            return 'hikvision'
                        elif 'cam/realmonitor' in url:
                            logger.info(f"✅ Detected Dahua DVR via URL: {url}")
                            return 'dahua'
                        elif '/ch' in url:
                            logger.info(f"✅ Detected Generic DVR via URL: {url}")
                            return 'generic'
                except Exception as e:
                    continue
                finally:
                    if cap is not None:
                        cap.release()
            
            # Default to generic
            logger.info("ℹ️ Brand detection failed, using generic")
            return 'generic'
            
        except Exception as e:
            logger.warning(f"⚠️ Brand detection failed: {e}")
            return 'generic'
    
    def generate_rtsp_urls(self, ip_address: str, username: str, password: str, 
                          rtsp_port: int, channel_number: int, brand: str = None) -> List[str]:
        """Generate multiple RTSP URLs for a channel"""
        urls = []
        
        # Detect brand if not provided
        if not brand:
            brand = self.detect_dvr_brand(ip_address, username, password, rtsp_port)
            logger.info(f"🔍 Detected DVR brand: {brand}")
        
        # Get brand-specific patterns
        patterns = self.dvr_url_patterns.get(brand, self.dvr_url_patterns['generic'])
        
        # Prepare safe credentials
        safe_username = urllib.parse.quote(username)
        safe_password = urllib.parse.quote(password)
        
        # Generate URLs for this brand
        for pattern in patterns:
            try:
                # Support patterns that embed {username}/{password} in the path (XM style)
                path = pattern.format(channel=channel_number, username=safe_username, password=safe_password)
                if path.startswith('/user=') or 'stream=0.sdp' in path or 'stream=1.sdp' in path:
                    # XM style requires no user:pass@ in authority
                    url = f"rtsp://{ip_address}:{rtsp_port}{path}"
                else:
                    url = f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}{path}"
                urls.append(url)
            except Exception as e:
                logger.warning(f"⚠️ Failed to generate URL for pattern {pattern}: {e}")

        # Always include the two known-good universal patterns regardless of brand
        try:
            urls.insert(0, f"rtsp://{ip_address}:{rtsp_port}/user={safe_username}&password={safe_password}&channel={channel_number}&stream=0.sdp")
            urls.insert(1, f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0")
        except Exception:
            pass
        
        # Add channel-specific variations based on channel number
        if channel_number <= 4:
            # For low channel numbers, try more variations
            urls.extend([
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number}/main",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number}/sub",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number}/0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number}/1",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1"
            ])
        elif channel_number <= 8:
            # For medium channel numbers
            urls.extend([
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/main",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/sub",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/1",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1"
            ])
        else:
            # For high channel numbers, try more specific patterns
            urls.extend([
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/main",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/sub",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/1",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/live/ch{channel_number:02d}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/live/channel{channel_number}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/live/camera{channel_number}"
            ])
        
        # Add brand-specific variations
        if brand == 'hikvision':
            # Hikvision çoğunlukla 101,201,... biçiminde indeks kullanır
            # channel_number 1 -> 101, 2 -> 201 ...
            major = channel_number * 100 + 1
            urls.extend([
                # Common Hikvision ISAPI variants (case differences across firmwares)
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{major}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{major+1}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{major+2}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/Channels/{major}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/Channels/{major+1}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/Channels/{major+2}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/streaming/channels/{major}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/streaming/channels/{major+1}",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/ISAPI/streaming/channels/{major+2}"
            ])
        elif brand == 'dahua':
            urls.extend([
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0&stream=0",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1&stream=1",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0&authbasic=1",
                f"rtsp://{safe_username}:{safe_password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1&authbasic=1"
            ])
        elif brand == 'xm':
            # Ensure XM variants are present explicitly
            urls.extend([
                f"rtsp://{ip_address}:{rtsp_port}/user={safe_username}&password={safe_password}&channel={channel_number}&stream=0.sdp",
                f"rtsp://{ip_address}:{rtsp_port}/user={safe_username}&password={safe_password}&channel={channel_number}&stream=1.sdp",
            ])
        
        # Remove duplicates while preserving order
        unique_urls = []
        seen = set()
        for url in urls:
            if url not in seen:
                unique_urls.append(url)
                seen.add(url)
        
        logger.info(f"🎯 Generated {len(unique_urls)} RTSP URLs for channel {channel_number} (brand: {brand})")
        return unique_urls

    def _create_capture_tcp(self, url: str, open_timeout: int = None, read_timeout: int = None) -> cv2.VideoCapture:
        """TCP-enforced VideoCapture factory.
        
        Tüm RTSP bağlantıları bu method üzerinden oluşturulmalıdır.
        Bu sayede:
        1. RTSP TCP zorlaması tek bir noktadan yönetilir
        2. Timeout değerleri tutarlı olur
        3. FFmpeg parametreleri standardize edilir
        """
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, open_timeout or self.connection_timeout)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, read_timeout or self.read_timeout)
        # Buffer boyutunu küçük tut — düşük gecikme (low latency) için
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _cache_success_url(self, ip_address: str, channel_number: int, url: str):
        """Başarılı RTSP URL'yi hem bellek cache'ine hem veritabanına kaydet."""
        cache_key = f"{ip_address}:{channel_number}"
        self._success_url_cache[cache_key] = url
        # TTL success cache (prevents immediate re-discovery storms)
        self._ttl_set(self._probe_success_ttl, cache_key, url, self._probe_ttl_success_s)
        logger.info(f"⚡ URL cached: {cache_key} → {redact_url(str(url))}")

        # Veritabanına da kaydet (persistent cache)
        try:
            from database.database_adapter import DatabaseAdapter
            db = DatabaseAdapter()
            db.update_channel_rtsp_path(ip_address, channel_number, url)
        except Exception as e:
            logger.debug(f"ℹ️ DB URL cache kayıt edilemedi (non-critical): {e}")

    def _get_cached_url(self, ip_address: str, channel_number: int) -> Optional[str]:
        """Bellekte veya veritabanında kayıtlı başarılı URL'yi getir."""
        cache_key = f"{ip_address}:{channel_number}"
        
        # 1. Önce bellek cache'ini kontrol et (en hızlı)
        cached = self._success_url_cache.get(cache_key)
        if cached:
            return cached

        # 2. Veritabanını kontrol et (persistent)
        try:
            from database.database_adapter import DatabaseAdapter
            db = DatabaseAdapter()
            db_url = db.get_channel_cached_rtsp_path(ip_address, channel_number)
            if db_url:
                # Bellek cache'ine de yükle
                self._success_url_cache[cache_key] = db_url
                logger.info(f"⚡ URL loaded from DB cache: {cache_key} → {db_url}")
                return db_url
        except Exception as e:
            logger.debug(f"ℹ️ DB URL cache okunamadı (non-critical): {e}")

        return None

    def find_working_url(self, ip_address: str, username: str, password: str,
                         rtsp_port: int, channel_number: int, brand: str = None) -> Optional[str]:
        """Deep scan for a working RTSP URL for a specific channel.
        
        Strateji (Cache-First, Discovery-Fallback):
        1. Önce cache'te kayıtlı URL'yi dene → <500ms
        2. Cache boşsa veya çalışmazsa → tam discovery taraması
        3. Başarılı URL'yi cache'e kaydet
        """
        # ── Phase 1: Cache'ten hızlı bağlantı ────────────────────────────
        # TTL success cache
        ttl_key = f"{ip_address}:{channel_number}"
        ttl_hit = self._ttl_get(self._probe_success_ttl, ttl_key)
        if ttl_hit:
            return ttl_hit
        # TTL fail cache
        if self._ttl_get(self._probe_fail_ttl, ttl_key) is not None:
            return None

        cached_url = self._get_cached_url(ip_address, channel_number)
        if cached_url:
            cap = None
            try:
                with self._probe_sem:
                    cap = self._create_capture_tcp(cached_url, open_timeout=2000, read_timeout=2000)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        logger.info(f"⚡ Cache HIT — channel {channel_number} connected instantly via cached URL")
                        cap.release()
                        self._ttl_set(self._probe_success_ttl, ttl_key, cached_url, self._probe_ttl_success_s)
                        return cached_url
                logger.info(f"⚠️ Cache MISS — cached URL no longer works, starting full discovery...")
            except Exception:
                pass
            finally:
                if cap:
                    cap.release()
            # Cache artık geçersiz, temizle
            cache_key = f"{ip_address}:{channel_number}"
            self._success_url_cache.pop(cache_key, None)

        # ── Phase 2: Full Discovery (brute-force tarama) ─────────────────
        urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number, brand)
        
        logger.info(f"🔍 Discovery: Scanning {len(urls)} patterns for channel {channel_number}...")
        
        for i, url in enumerate(urls[: max(1, self._start_url_budget)]):
            cap = None
            try:
                with self._probe_sem:
                    cap = self._create_capture_tcp(url, open_timeout=1500, read_timeout=1500)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        logger.info(f"✅ Works! Formula found for channel {channel_number} (URL {i+1}): {redact_url(str(url))}")
                        cap.release()
                        # Başarılı URL'yi cache'e kaydet
                        self._cache_success_url(ip_address, channel_number, url)
                        self._ttl_set(self._probe_success_ttl, ttl_key, url, self._probe_ttl_success_s)
                        return url
            except Exception:
                pass
            finally:
                if cap:
                    cap.release()
                    
        logger.warning(f"❌ Discovery: No working pattern found for channel {channel_number}")
        self._ttl_set(self._probe_fail_ttl, ttl_key, "1", self._probe_ttl_fail_s)
        return None

    def detect_available_channels(self, ip_address: str, username: str, password: str,
                                  rtsp_port: int, max_channels: int = 32) -> List[int]:
        """Probe DVR to detect which channel numbers are available.

        Strategy (ONVIF-first, RTSP-fallback):
        1. Try ONVIF channel enumeration — instant, ~2 seconds
        2. Fallback: parallel RTSP probe with ThreadPoolExecutor — ~30 seconds
        """
        available_channels: List[int] = []
        ttl_key = f"channels:{ip_address}:{rtsp_port}"
        cached = self._ttl_get(self._probe_success_ttl, ttl_key)
        if cached:
            try:
                return sorted([int(x) for x in cached.split(",") if x.strip().isdigit()])
            except Exception:
                pass

        # ── Phase 1: ONVIF Channel Enumeration (fast path) ──────────────
        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            onvif_mgr = get_onvif_manager()
            onvif_channels = onvif_mgr.enumerate_channels(
                ip_address, port=80, username=username, password=password
            )
            if onvif_channels:
                available_channels = [ch['channel_number'] for ch in onvif_channels
                                      if ch.get('stream_uri')]
                if available_channels:
                    logger.info(
                        f"✅ ONVIF kanal keşfi: {ip_address} — "
                        f"{len(available_channels)} kanal bulundu (anında)"
                    )
                    # Cache ONVIF URIs for later use by start_stream
                    for ch in onvif_channels:
                        if ch.get('stream_uri'):
                            cache_key = f"{ip_address}:{ch['channel_number']}"
                            self._onvif_uri_cache[cache_key] = ch['stream_uri']
                    return sorted(available_channels)
        except Exception as e:
            logger.debug(f"ℹ️ ONVIF kanal keşfi başarısız, RTSP probe'a geçiliyor: {e}")

        # ── Phase 2: Parallel RTSP Probe (fallback) ─────────────────────
        try:
            if not self.test_network_connectivity(ip_address, rtsp_port):
                logger.error(f"❌ No network connectivity to {ip_address}:{rtsp_port}")
                return available_channels

            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _probe_channel(channel: int) -> int:
                """Probe a single channel — returns channel number or -1."""
                urls = self.generate_rtsp_urls(
                    ip_address, username, password, rtsp_port, channel
                )
                for url in urls[: max(1, self._probe_url_budget)]:  # retry budget per channel
                    cap = None
                    try:
                        with self._probe_sem:
                            cap = cv2.VideoCapture(url)
                            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500)
                            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500)
                        if cap.isOpened():
                            ret, frame = cap.read()
                            if ret and frame is not None:
                                logger.info(f"✅ Channel probe success: {channel} via {url}")
                                return channel
                    except Exception:
                        pass
                    finally:
                        if cap:
                            cap.release()
                return -1

            with ThreadPoolExecutor(max_workers=max(1, self._channel_probe_workers)) as executor:
                futures = {
                    executor.submit(_probe_channel, ch): ch
                    for ch in range(1, max_channels + 1)
                }
                for future in as_completed(futures, timeout=60):
                    try:
                        result = future.result()
                        if result > 0:
                            available_channels.append(result)
                    except Exception:
                        continue

        except Exception as e:
            logger.error(f"❌ Channel detection error: {e}")

        # Ensure unique and sorted
        out = sorted(list(set(available_channels)))
        if out:
            self._ttl_set(self._probe_success_ttl, ttl_key, ",".join(str(x) for x in out), self._probe_ttl_success_s)
        else:
            self._ttl_set(self._probe_fail_ttl, ttl_key, "1", self._probe_ttl_fail_s)
        return out
    
    def test_network_connectivity(self, ip_address: str, rtsp_port: int) -> bool:
        """Test basic network connectivity to DVR"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip_address, rtsp_port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.error(f"❌ Network connectivity test failed: {e}")
            return False
    
    def start_stream(
        self,
        stream_id: str,
        rtsp_url: str,
        ip_address: str = None,
        username: str = None,
        password: str = None,
        rtsp_port: int = None,
        channel_number: int = None,
        sector: Optional[str] = None,
        company_id: Optional[str] = None,
        required_ppe: Optional[list] = None,
    ) -> bool:
        """Start streaming with ONVIF-first URL resolution + fallback to guessed URL."""
        try:
            # ── ONVIF URI resolution: prefer device-provided URI ─────────
            effective_url = rtsp_url
            if ip_address and channel_number:
                onvif_uri = self._try_onvif_stream_uri(
                    ip_address, username, password, channel_number
                )
                if onvif_uri:
                    effective_url = onvif_uri
                    logger.info(
                        f"✅ ONVIF URI kullanılıyor: {stream_id} kanal {channel_number}"
                    )

            if stream_id in self.active_streams:
                existing_status = self.active_streams[stream_id].get('status')
                if existing_status == 'active':
                    logger.warning(f"⚠️ Stream already active: {stream_id}")
                    # Ensure frame buffer exists even if stream was started elsewhere
                    if stream_id not in self.frame_buffers:
                        self.frame_buffers[stream_id] = []
                    return True
                else:
                    # Restart stream if present but not active
                    logger.info(f"🔄 Stream {stream_id} is in status '{existing_status}', restarting...")
                    self.active_streams[stream_id].update({
                        'rtsp_url': effective_url,
                        'status': 'starting',
                        'start_time': time.time(),
                        'frame_count': 0,
                        'error_count': 0,
                        'ip_address': ip_address,
                        'username': username,
                        'password': password,
                        'rtsp_port': rtsp_port,
                        'channel_number': channel_number,
                        'sector': sector or self.active_streams[stream_id].get('sector'),
                    })
                    self._ensure_stream_config(
                        stream_id,
                        company_id=company_id,
                        sector=sector,
                        required_ppe=required_ppe,
                    )
                    self._transition(stream_id, "starting", reason="restart_requested", error_code=None)
                    if stream_id not in self.frame_buffers:
                        self.frame_buffers[stream_id] = []
                    thread = threading.Thread(
                        target=self._stream_worker,
                        args=(stream_id, effective_url, ip_address, username, password, rtsp_port, channel_number),
                        daemon=True
                    )
                    thread.start()
                    return True
                
            # Initialize stream info
            self.active_streams[stream_id] = {
                'rtsp_url': effective_url,
                'status': 'starting',
                'start_time': time.time(),
                'frame_count': 0,
                'error_count': 0,
                'ip_address': ip_address,
                'username': username,
                'password': password,
                'rtsp_port': rtsp_port,
                'channel_number': channel_number,
                'sector': sector or 'construction',
                'status_reason': 'init',
                'last_error_code': None,
                'last_transition_ts': time.time(),
                'detection_result': {
                    'detections': [],
                    'people_detected': 0,
                    'compliance_rate': 100,
                    'ppe_violations': [],
                    'timestamp': time.time()
                }
            }
            self._ensure_stream_config(
                stream_id,
                company_id=company_id,
                sector=sector,
                required_ppe=required_ppe,
            )
            self._transition(stream_id, "starting", reason="start_requested", error_code=None)
            
            self.frame_buffers[stream_id] = []
            
            # Start streaming thread
            thread = threading.Thread(
                target=self._stream_worker,
                args=(stream_id, effective_url, ip_address, username, password, rtsp_port, channel_number),
                daemon=True
            )
            thread.start()
            
            logger.info(f"✅ Stream started: {stream_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Start stream error: {e}")
            return False

    _onvif_fail_cache: Dict[str, float] = {}
    _ONVIF_FAIL_TTL = 300  # 5 min

    def _try_onvif_stream_uri(self, ip_address: str, username: str,
                              password: str, channel_number: int) -> Optional[str]:
        """Try to get stream URI via ONVIF. Returns URI or None on failure."""
        cache_key = f"{ip_address}:{channel_number}"

        cached = self._onvif_uri_cache.get(cache_key)
        if cached:
            return cached

        fail_ts = self._onvif_fail_cache.get(ip_address, 0)
        if time.time() - fail_ts < self._ONVIF_FAIL_TTL:
            return None

        try:
            from integrations.cameras.onvif_discovery import get_onvif_manager
            onvif_mgr = get_onvif_manager()
            uri = onvif_mgr.get_stream_uri(
                ip_address, port=80,
                username=username, password=password,
                profile_index=max(0, channel_number - 1),
            )
            if uri:
                self._onvif_uri_cache[cache_key] = uri
            return uri
        except Exception as e:
            self._onvif_fail_cache[ip_address] = time.time()
            logger.debug(f"ONVIF URI alınamadı ({ip_address}), 5dk boyunca tekrar denenmeyecek: {e}")
            return None
    
    def stop_stream(self, stream_id: str) -> bool:
        """Stop streaming"""
        try:
            with self._lock:
                if stream_id in self.active_streams:
                    self._transition(stream_id, "stopping", reason="stop_requested", error_code=None)
                    logger.info(f"🛑 Stream stopping: {stream_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Stop stream error: {e}")
            return False
    
    def get_latest_frame(self, stream_id: str) -> Optional[str]:
        """Get latest frame as base64 encoded JPEG"""
        try:
            with self._lock:
                if stream_id in self.frame_buffers and self.frame_buffers[stream_id]:
                    frame_data = self.frame_buffers[stream_id][-1]
                    if frame_data and len(frame_data) > 0:
                        return frame_data
                    else:
                        logger.warning(f"⚠️ Empty frame data for {stream_id}")
                        return None
                else:
                    logger.warning(f"⚠️ No frame buffer for {stream_id}")
                    self.frame_buffers[stream_id] = []
                return None
        except Exception as e:
            logger.error(f"❌ Get frame error for {stream_id}: {e}")
            return None
    
    def get_stream_status(self, stream_id: str) -> Optional[Dict]:
        """Get stream status"""
        try:
            with self._lock:
                if stream_id in self.active_streams:
                    return dict(self.active_streams[stream_id])
                return None
        except Exception as e:
            logger.error(f"❌ Get status error: {e}")
            return None
    
    def _perform_ppe_detection(self, frame, stream_id: str, use_pose: bool = True,
                               sector: Optional[str] = None) -> Dict:
        """Perform PPE detection on a frame. sector eksikse stream metadata'dan al."""
        try:
            required_ppe = None
            cfg = None
            if stream_id in self.active_streams:
                cfg = self.active_streams[stream_id].get("immutable_config") or {}

            # Sektör önceŏli olarak dışarıdan alınır; yoksa immutable config / stream metadata'ya bak.
            if not sector:
                sector = (cfg.get("sector") if isinstance(cfg, dict) else None) or (
                    self.active_streams[stream_id].get('sector') if stream_id in self.active_streams else None
                )
            if isinstance(cfg, dict):
                required_ppe = cfg.get("required_ppe")

            # Sektör hala bilinemiyorsa varsayılan kullan.
            if not sector:
                sector = 'construction'
                logger.debug(f"⚠️ Stream {stream_id}: sector belirlenemedi, varsayılan 'construction' kullanılıyor")

            # 🚀 FAZ 3: POSE-AWARE DETECTION FOR DVR/NVR — Singleton model
            if use_pose:
                try:
                    from detection.pose_aware_ppe_detector import get_pose_aware_detector
                    from models.sh17_model_manager import SH17ModelManager

                    # Lazy singleton: ilk çağrıda oluştur, sonra yeniden kullan.
                    if self._sh17_manager is None:
                        self._sh17_manager = SH17ModelManager()
                        logger.info("✅ DVRStreamHandler: SH17ModelManager singleton oluşturuldu")
                    if self._pose_detector is None:
                        self._pose_detector = get_pose_aware_detector(ppe_detector=self._sh17_manager)
                        logger.info("✅ DVRStreamHandler: PoseAwarePPEDetector singleton oluşturuldu")

                    logger.debug(f"🎯 Pose-aware detection: stream={stream_id}, sector={sector}")
                    result = self._pose_detector.detect_with_pose(frame, sector, confidence=0.25)
                    if isinstance(result, dict):
                        return result
                    if isinstance(result, list):
                        people = len([d for d in result if isinstance(d, dict) and d.get('class_name') == 'person'])
                        return {
                            'detections': result,
                            'people_detected': people,
                            'compliance_rate': 100,
                            'ppe_violations': [],
                            'timestamp': time.time(),
                            'sector': sector,
                            'model_type': 'PoseAware',
                        }

                except Exception as pose_error:
                    logger.warning(f"⚠️ DVR Pose-aware detection failed, falling back to standard: {pose_error}")
                    # Fall through to standard detection

            # 🎯 FAZ 1-2: STANDARD DETECTION (FALLBACK)
            from models.sh17_model_manager import SH17ModelManager
            if self._sh17_manager is None:
                self._sh17_manager = SH17ModelManager()
                logger.info("✅ DVRStreamHandler: SH17ModelManager singleton oluşturuldu (fallback)")

            detections = self._sh17_manager.detect_ppe(frame, sector=sector, confidence=0.25)
            people_detected = len([d for d in detections if isinstance(d, dict) and d.get('class_name') == 'person'])
            if not required_ppe:
                required_ppe = self._sh17_manager.get_sector_requirements(sector)
            compliance_analysis = self._sh17_manager.analyze_compliance(detections, required_ppe)

            return {
                'detections': detections if isinstance(detections, list) else [],
                'people_detected': people_detected,
                'compliance_rate': int(compliance_analysis.get('score', 0) * 100) if isinstance(compliance_analysis, dict) else 100,
                'ppe_violations': compliance_analysis.get('missing', []) if isinstance(compliance_analysis, dict) else [],
                'timestamp': time.time(),
                'sector': sector,
                'model_type': 'SH17' if self._sh17_manager.is_sh17_available(sector) else 'Fallback'
            }

        except Exception as e:
            logger.error(f"❌ PPE Detection error: {e}")
            return {
                'detections': [],
                'people_detected': 0,
                'compliance_rate': 100,
                'ppe_violations': [],
                'timestamp': time.time(),
                'sector': sector or 'unknown',
                'model_type': 'Error'
            }

    def get_latest_detection_result(self, stream_id: str) -> Optional[Dict]:
        """Get latest detection result for a stream - Bounding Box Overlay için"""
        try:
            if stream_id in self.active_streams:
                stream_info = self.active_streams[stream_id]
                # Detection result'ı stream_info'dan al
                detection_result = stream_info.get('detection_result', {})
                
                if detection_result:
                    return {
                        'detections': detection_result.get('detections', []),
                        'people_detected': detection_result.get('people_detected', 0),
                        'compliance_rate': detection_result.get('compliance_rate', 100),
                        'ppe_violations': detection_result.get('ppe_violations', []),
                        'timestamp': detection_result.get('timestamp', ''),
                        'camera_id': stream_info.get('camera_id', 'unknown')
                    }
                
            return None
            
        except Exception as e:
            logger.error(f"❌ Detection result alma hatası: {e}")
            return None

    def capture_single_frame(self, ip_address: str, username: str, password: str,
                              rtsp_port: int, channel_number: int) -> Optional[str]:
        """Open RTSP briefly, grab a single frame, and close (base64). Designed to be fast and resilient for previews."""
        # ONVIF cache: if we already resolved this channel's URI, try it first
        candidates = []
        cache_key = f"{ip_address}:{channel_number}"
        cached_uri = self._onvif_uri_cache.get(cache_key)
        if cached_uri:
            candidates.append(cached_uri)

        urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
        # Try a very small subset first for speed (most likely to work)
        candidates.extend(urls[:4])

        for url in candidates:
            cap = None
            try:
                cap = cv2.VideoCapture(url)
                # Conservative timeouts to avoid blocking the endpoint
                try:
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1200)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1200)
                except Exception:
                    pass
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        try:
                            # Lower quality for preview grid to reduce payload
                            _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                            return base64.b64encode(jpeg_data).decode('utf-8')
                        except Exception:
                            return None
            except Exception:
                continue
            finally:
                if cap:
                    cap.release()
        return None

    # --- Lightweight image hashing utilities for stream verification ---
    @staticmethod
    def _compute_average_hash_from_frame(frame) -> Optional[int]:
        try:
            import cv2
            import numpy as np
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
            avg = small.mean()
            bits = (small > avg).astype(np.uint8).flatten()
            # Pack 64 bits into an integer
            value = 0
            for b in bits:
                value = (value << 1) | int(b)
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _hamming_distance64(a: int, b: int) -> int:
        x = (a ^ b) & ((1 << 64) - 1)
        # builtin popcount for Python 3.8+:
        return x.bit_count() if hasattr(int, 'bit_count') else bin(x).count('1')
    
    def _stream_worker(self, stream_id: str, rtsp_url: str, 
                      ip_address: str = None, username: str = None, 
                      password: str = None, rtsp_port: int = None, 
                      channel_number: int = None):
        """Enhanced worker thread for streaming with multiple URL fallbacks"""
        cap = None
        max_reconnect_attempts = 3
        reconnect_delay = 5  # seconds
        
        try:
            logger.info(f"🎥 Opening RTSP stream: {stream_id} -> {rtsp_url}")
            
            # Test network connectivity first
            if ip_address and rtsp_port:
                if not self.test_network_connectivity(ip_address, rtsp_port):
                    logger.error(f"❌ No network connectivity to {ip_address}:{rtsp_port}")
                    self._transition(stream_id, "error", reason="no_network_connectivity", error_code="NO_NETWORK")
                    return
            
            # ── Cache-First Strategy: Önce kayıtlı URL'yi dene ────────────
            cap = None
            successful_url = None

            if ip_address and channel_number:
                cached_url = self._get_cached_url(ip_address, channel_number)
                if cached_url:
                    try:
                        cap = self._create_capture_tcp(cached_url)
                        if cap.isOpened():
                            ret, test_frame = cap.read()
                            if ret and test_frame is not None:
                                logger.info(f"⚡ Channel {channel_number}: Instant connect via cached URL")
                                successful_url = cached_url
                    except Exception:
                        pass
                    if not successful_url:
                        if cap:
                            cap.release()
                            cap = None
                        logger.info(f"⚠️ Channel {channel_number}: Cached URL stale, falling back to discovery")

            # ── Full Discovery (yalnızca cache çalışmazsa) ───────────────
            if not successful_url:
                urls_to_try = [rtsp_url]  # Start with original URL

                # Add brand-specific URLs if we have the parameters
                if all([ip_address, username, password, rtsp_port, channel_number]):
                    brand_urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
                    urls_to_try.extend(brand_urls)
                    logger.info(f"🎯 Channel {channel_number}: Will try {len(urls_to_try)} different URL patterns")
                else:
                    logger.warning(f"⚠️ Channel {channel_number}: Missing parameters for enhanced URL generation")

                # Prioritize vendor-specific working URLs
                def _prio(u: str) -> tuple:
                    is_xm = ('stream=0.sdp' in u or 'stream=1.sdp' in u) and '/user=' in u
                    is_cam = 'cam/realmonitor' in u
                    is_isapi = "ISAPI/Streaming/channels" in u
                    is_ch_main = "/ch" in u and u.endswith("/main")
                    return ((0 if is_xm else (1 if is_cam else (2 if is_isapi else (3 if is_ch_main else 4)))), u)
                urls_to_try.sort(key=_prio)

                for i, url in enumerate(urls_to_try):
                    try:
                        logger.info(f"🔄 Channel {channel_number}: Trying RTSP URL {i+1}/{len(urls_to_try)}: {url}")

                        cap = self._create_capture_tcp(url)

                        if cap.isOpened():
                            ret, test_frame = cap.read()
                            if ret and test_frame is not None:
                                logger.info(f"✅ Channel {channel_number}: Successfully opened RTSP stream: {url}")
                                successful_url = url
                                break
                            else:
                                logger.warning(f"⚠️ Channel {channel_number}: Failed to read frame: {url}")
                                if cap:
                                    cap.release()
                                    cap = None
                        else:
                            logger.warning(f"⚠️ Channel {channel_number}: Failed to open URL: {url}")
                            if cap:
                                cap.release()
                                cap = None

                    except Exception as e:
                        logger.warning(f"⚠️ Channel {channel_number}: Failed to open URL {url}: {e}")
                        if cap:
                            cap.release()
                            cap = None
                        continue

            if not cap or not cap.isOpened():
                logger.error(f"❌ Failed to open any RTSP stream for {stream_id}")
                self._transition(stream_id, "error", reason="open_failed", error_code="OPEN_FAILED")
                return

            # ── Başarılı URL'yi cache'e kaydet ───────────────────────────
            if successful_url and ip_address and channel_number:
                self._cache_success_url(ip_address, channel_number, successful_url)

            # Update stream info with successful URL
            self.active_streams[stream_id]['rtsp_url'] = successful_url
            self._transition(stream_id, "active", reason="stream_opened", error_code=None)
            logger.info(f"✅ RTSP stream opened successfully: {stream_id} -> {successful_url}")
            
            # Immediately try to read a frame to ensure stream is working
            try:
                ret, test_frame = cap.read()
                if ret and test_frame is not None:
                    # Convert test frame to JPEG and add to buffer
                    _, jpeg_data = cv2.imencode('.jpg', test_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                    
                    if stream_id in self.frame_buffers:
                        self.frame_buffers[stream_id].append(jpeg_base64)
                    
                    logger.info(f"✅ Initial frame captured for {stream_id}")
                else:
                    logger.warning(f"⚠️ Initial frame read failed for {stream_id}")
            except Exception as e:
                logger.warning(f"⚠️ Initial frame processing failed for {stream_id}: {e}")
            
            frame_count = 0
            consecutive_errors = 0
            max_consecutive_errors = 10
            
            while self.active_streams.get(stream_id, {}).get('status') == 'active':
                try:
                    ret, frame = cap.read()
                    
                    if not ret or frame is None:
                        consecutive_errors += 1
                        logger.warning(f"⚠️ Failed to read frame from {stream_id} (error {consecutive_errors}/{max_consecutive_errors})")
                        
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(f"❌ Too many consecutive errors for {stream_id}, attempting reconnection...")
                            
                            # Try to reconnect
                            cap.release()
                            cap = None
                            
                            # Try reconnection with different URLs
                            for attempt in range(max_reconnect_attempts):
                                logger.info(f"🔄 Channel {channel_number}: Reconnection attempt {attempt + 1}/{max_reconnect_attempts}")
                                
                                if all([ip_address, username, password, rtsp_port, channel_number]):
                                    reconnect_urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
                                    logger.info(f"🔄 Channel {channel_number}: Trying {len(reconnect_urls)} URLs for reconnection")
                                else:
                                    reconnect_urls = [successful_url] if successful_url else urls_to_try
                                
                                for url in reconnect_urls:
                                    try:
                                        cap = self._create_capture_tcp(url)
                                        
                                        if cap.isOpened():
                                            ret, test_frame = cap.read()
                                            if ret and test_frame is not None:
                                                logger.info(f"✅ Channel {channel_number}: Reconnection successful: {url}")
                                                successful_url = url
                                                consecutive_errors = 0
                                                # Yeni çalışan URL'yi cache'e güncelle
                                                if ip_address and channel_number:
                                                    self._cache_success_url(ip_address, channel_number, url)
                                                break
                                            else:
                                                cap.release()
                                                cap = None
                                    except Exception as e:
                                        logger.warning(f"⚠️ Channel {channel_number}: Reconnection attempt failed for {url}: {e}")
                                        if cap:
                                            cap.release()
                                            cap = None
                                
                                if cap and cap.isOpened():
                                    break
                                
                                time.sleep(reconnect_delay)
                            
                            if not cap or not cap.isOpened():
                                logger.error(f"❌ Reconnection failed for {stream_id}")
                                self._transition(stream_id, "error", reason="reconnect_failed", error_code="RECONNECT_FAILED")
                                break
                        
                        time.sleep(0.1)
                        continue
                    
                    # Reset error count on successful frame
                    consecutive_errors = 0
                    
                    # Convert frame to JPEG
                    try:
                        # Frame quality'yi düşür ve boyutu optimize et
                        _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                        
                        # Add to buffer - Optimized buffer management
                        if stream_id in self.frame_buffers:
                            buffer = self.frame_buffers[stream_id]
                            buffer.append(jpeg_base64)
                            
                            # Keep only latest frames - Smaller buffer for smoother playback
                            if len(buffer) > 5:  # Reduced from max_buffer_size to 5
                                buffer.pop(0)
                        
                        frame_count += 1
                        self.active_streams[stream_id]['frame_count'] = frame_count
                        
                        # 🎯 PPE DETECTION - Her 15 frame'de bir detection yap (increased frequency)
                        detection_frequency = self.active_streams[stream_id].get('detection_frequency', 15)
                        if frame_count % detection_frequency == 0:
                            try:
                                # Singleton modeli kullanan _perform_ppe_detection çağrısı
                                detection_result = self._perform_ppe_detection(
                                    frame, stream_id,
                                    sector=self.active_streams[stream_id].get('sector')
                                )
                                # Stream info'ya detection result'ı ekle
                                if stream_id in self.active_streams:
                                    self.active_streams[stream_id]['detection_result'] = detection_result
                                logger.debug(f"🎯 {stream_id}: Detection completed - People: {detection_result.get('people_detected', 0)}, PPE: {len(detection_result.get('detections', []))}")
                            except Exception as e:
                                logger.warning(f"⚠️ Detection error for {stream_id}: {e}")
                        
                        # Log progress every 120 frames (reduced frequency for performance)
                        if frame_count % 120 == 0:
                            logger.info(f"📊 {stream_id}: {frame_count} frames captured")
                        
                        # 🚀 FRAME SKIP OPTIMIZATION - Her 3 frame'de bir işle (smooth playback)
                        if frame_count % 3 == 0:
                            # Frame quality'yi düşür ve boyutu optimize et
                            _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                            jpeg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                            
                            # Add to buffer - Optimized buffer management
                            if stream_id in self.frame_buffers:
                                buffer = self.frame_buffers[stream_id]
                                buffer.append(jpeg_base64)
                                
                                # Keep only latest frames - Smaller buffer for smoother playback
                                if len(buffer) > 3:  # Reduced buffer size for faster switching
                                    buffer.pop(0)
                        
                    except Exception as e:
                        logger.error(f"❌ Frame processing error for {stream_id}: {e}")
                    
                    # Optimized frame rate control - Reduced delay for smoother playback
                    time.sleep(0.015)  # ~65 FPS (increased from 50 FPS)
                    
                except Exception as e:
                    logger.error(f"❌ Stream read error for {stream_id}: {e}")
                    consecutive_errors += 1
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"❌ Stream worker error for {stream_id}: {e}")
            if stream_id in self.active_streams:
                self._transition(stream_id, "error", reason="worker_exception", error_code="WORKER_EXCEPTION")
        finally:
            if cap:
                cap.release()
            if stream_id in self.active_streams:
                self._transition(stream_id, "stopped", reason="worker_exit", error_code=None)
            logger.info(f"🛑 Stream worker stopped: {stream_id}")

    def switch_channel_fast(self, stream_id: str, new_rtsp_url: str, 
                           ip_address: str = None, username: str = None, 
                           password: str = None, rtsp_port: int = None, 
                           channel_number: int = None) -> bool:
        """Hızlı kanal geçişi - Buffer temizleme ve frame skip ile"""
        try:
            logger.info(f"🚀 Hızlı kanal geçişi: {stream_id}")
            
            # Mevcut stream'i durdur
            if stream_id in self.active_streams:
                # Buffer'ı hızlı temizle
                if stream_id in self.frame_buffers:
                    self.frame_buffers[stream_id].clear()
                
                # Stream worker'ı durdur
                self.active_streams[stream_id]['active'] = False
                time.sleep(0.1)  # Kısa bekleme
            
            # Yeni stream'i başlat
            success = self.start_stream(stream_id, new_rtsp_url, ip_address, username, password, rtsp_port, channel_number)
            
            if success:
                logger.info(f"✅ Hızlı kanal geçişi tamamlandı: {stream_id}")
                return True
            else:
                logger.error(f"❌ Hızlı kanal geçişi başarısız: {stream_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Hızlı kanal geçişi hatası: {e}")
            return False
    
    def get_channel_preview(self, stream_id: str, preview_frames: int = 3) -> List[str]:
        """Kanal önizlemesi - Hızlı frame capture ile"""
        try:
            if stream_id not in self.active_streams:
                return []
            
            preview_frames_list = []
            buffer = self.frame_buffers.get(stream_id, [])
            
            # Son birkaç frame'i al
            if buffer:
                preview_frames_list = buffer[-preview_frames:] if len(buffer) >= preview_frames else buffer
            
            return preview_frames_list
            
        except Exception as e:
            logger.error(f"❌ Kanal önizleme hatası: {e}")
            return []
    
    def optimize_stream_performance(self, stream_id: str) -> bool:
        """Stream performansını optimize et - Detection sıklığını artır"""
        try:
            if stream_id not in self.active_streams:
                return False
            
            # Detection sıklığını artır (her 15 frame'de bir)
            self.active_streams[stream_id]['detection_frequency'] = 15
            
            # Buffer size'ı optimize et
            if stream_id in self.frame_buffers:
                # Buffer'ı küçült ama hızlı tut
                current_buffer = self.frame_buffers[stream_id]
                if len(current_buffer) > 3:
                    self.frame_buffers[stream_id] = current_buffer[-3:]
            
            logger.info(f"🚀 Stream performansı optimize edildi: {stream_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Stream optimizasyon hatası: {e}")
            return False

# Global stream handler instance
stream_handler = DVRStreamHandler()


def get_stream_handler() -> DVRStreamHandler:
    """Get global stream handler instance"""
    return stream_handler
