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
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

class DVRStreamHandler:
    """Advanced DVR stream handler with multi-brand support"""
    
    def __init__(self):
        self.active_streams: Dict[str, Dict] = {}
        self.frame_buffers: Dict[str, list] = {}
        self.max_buffer_size = 5  # Reduced from 10 to 5 for smoother playback
        self.connection_timeout = 3000  # Reduced from 5000 to 3000 ms for faster connection
        self.read_timeout = 2000  # Reduced from 3000 to 2000 ms for faster frame reading
        
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
        
    def detect_dvr_brand(self, ip_address: str, username: str, password: str, rtsp_port: int) -> str:
        """Detect DVR brand by testing common URL patterns"""
        try:
            # Test multiple channels for brand detection
            test_channels = [1, 2, 3]  # Test multiple channels
            test_urls = []
            
            for channel in test_channels:
                test_urls.extend([
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{channel}01",
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel}&subtype=0",
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel:02d}/main",
                    f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel:02d}/sub",
                    # XM-style credential-in-query
                    f"rtsp://{ip_address}:{rtsp_port}/user={username}&password={password}&channel={channel}&stream=0.sdp",
                ])
            
            for url in test_urls:
                try:
                    cap = cv2.VideoCapture(url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000)
                    if cap.isOpened():
                        cap.release()
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
        
        # Generate URLs for this brand
        for pattern in patterns:
            try:
                # Support patterns that embed {username}/{password} in the path (XM style)
                path = pattern.format(channel=channel_number, username=username, password=password)
                if path.startswith('/user=') or 'stream=0.sdp' in path or 'stream=1.sdp' in path:
                    # XM style requires no user:pass@ in authority
                    url = f"rtsp://{ip_address}:{rtsp_port}{path}"
                else:
                    url = f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}{path}"
                urls.append(url)
            except Exception as e:
                logger.warning(f"⚠️ Failed to generate URL for pattern {pattern}: {e}")

        # Always include the two known-good universal patterns regardless of brand
        try:
            urls.insert(0, f"rtsp://{ip_address}:{rtsp_port}/user={username}&password={password}&channel={channel_number}&stream=0.sdp")
            urls.insert(1, f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0")
        except Exception:
            pass
        
        # Add channel-specific variations based on channel number
        if channel_number <= 4:
            # For low channel numbers, try more variations
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/main",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/sub",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number}/1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1"
            ])
        elif channel_number <= 8:
            # For medium channel numbers
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/main",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/sub",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1"
            ])
        else:
            # For high channel numbers, try more specific patterns
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/main",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/sub",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ch{channel_number:02d}/1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/live/ch{channel_number:02d}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/live/channel{channel_number}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/live/camera{channel_number}"
            ])
        
        # Add brand-specific variations
        if brand == 'hikvision':
            # Hikvision çoğunlukla 101,201,... biçiminde indeks kullanır
            # channel_number 1 -> 101, 2 -> 201 ...
            major = channel_number * 100 + 1
            urls.extend([
                # Common Hikvision ISAPI variants (case differences across firmwares)
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{major}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{major+1}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/channels/{major+2}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/Channels/{major}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/Channels/{major+1}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/Streaming/Channels/{major+2}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/streaming/channels/{major}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/streaming/channels/{major+1}",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/ISAPI/streaming/channels/{major+2}"
            ])
        elif brand == 'dahua':
            urls.extend([
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0&stream=0",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1&stream=1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=0&authbasic=1",
                f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/cam/realmonitor?channel={channel_number}&subtype=1&authbasic=1"
            ])
        elif brand == 'xm':
            # Ensure XM variants are present explicitly
            urls.extend([
                f"rtsp://{ip_address}:{rtsp_port}/user={username}&password={password}&channel={channel_number}&stream=0.sdp",
                f"rtsp://{ip_address}:{rtsp_port}/user={username}&password={password}&channel={channel_number}&stream=1.sdp",
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

    def detect_available_channels(self, ip_address: str, username: str, password: str,
                                  rtsp_port: int, max_channels: int = 32) -> List[int]:
        """Probe DVR to detect which channel numbers are available.

        Tries multiple brand-specific URL patterns per channel and returns
        a list of channel numbers that successfully yielded at least one frame.
        """
        available_channels: List[int] = []

        try:
            if not self.test_network_connectivity(ip_address, rtsp_port):
                logger.error(f"❌ No network connectivity to {ip_address}:{rtsp_port}")
                return available_channels

            for channel in range(1, max_channels + 1):
                try:
                    urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel)
                    found = False
                    for url in urls[:8]:  # limit attempts per channel for speed
                        cap = None
                        try:
                            cap = cv2.VideoCapture(url)
                            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 1500)
                            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500)
                            if cap.isOpened():
                                ret, frame = cap.read()
                                if ret and frame is not None:
                                    available_channels.append(channel)
                                    found = True
                                    logger.info(f"✅ Channel probe success: {channel} via {url}")
                                    break
                        except Exception:
                            pass
                        finally:
                            if cap:
                                cap.release()
                    if not found:
                        logger.debug(f"ℹ️ Channel probe failed: {channel}")
                except Exception as e:
                    logger.warning(f"⚠️ Channel probe error for channel {channel}: {e}")
                    continue
        except Exception as e:
            logger.error(f"❌ Channel detection error: {e}")

        # Ensure unique and sorted
        return sorted(list(set(available_channels)))
    
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
    
    def start_stream(self, stream_id: str, rtsp_url: str, 
                    ip_address: str = None, username: str = None, 
                    password: str = None, rtsp_port: int = None, 
                    channel_number: int = None) -> bool:
        """Start streaming with enhanced URL handling"""
        try:
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
                        'rtsp_url': rtsp_url,
                        'status': 'starting',
                        'start_time': time.time(),
                        'frame_count': 0,
                        'error_count': 0,
                        'ip_address': ip_address,
                        'username': username,
                        'password': password,
                        'rtsp_port': rtsp_port,
                        'channel_number': channel_number
                    })
                    if stream_id not in self.frame_buffers:
                        self.frame_buffers[stream_id] = []
                    thread = threading.Thread(
                        target=self._stream_worker,
                        args=(stream_id, rtsp_url, ip_address, username, password, rtsp_port, channel_number),
                        daemon=True
                    )
                    thread.start()
                    return True
                
            # Initialize stream info
            self.active_streams[stream_id] = {
                'rtsp_url': rtsp_url,
                'status': 'starting',
                'start_time': time.time(),
                'frame_count': 0,
                'error_count': 0,
                'ip_address': ip_address,
                'username': username,
                'password': password,
                'rtsp_port': rtsp_port,
                'channel_number': channel_number,
                'detection_result': {
                    'detections': [],
                    'people_detected': 0,
                    'compliance_rate': 100,
                    'ppe_violations': [],
                    'timestamp': time.time()
                }
            }
            
            self.frame_buffers[stream_id] = []
            
            # Start streaming thread
            thread = threading.Thread(
                target=self._stream_worker,
                args=(stream_id, rtsp_url, ip_address, username, password, rtsp_port, channel_number),
                daemon=True
            )
            thread.start()
            
            logger.info(f"✅ Stream started: {stream_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Start stream error: {e}")
            return False
    
    def stop_stream(self, stream_id: str) -> bool:
        """Stop streaming"""
        try:
            if stream_id in self.active_streams:
                self.active_streams[stream_id]['status'] = 'stopping'
                logger.info(f"🛑 Stream stopping: {stream_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Stop stream error: {e}")
            return False
    
    def get_latest_frame(self, stream_id: str) -> Optional[str]:
        """Get latest frame as base64 encoded JPEG"""
        try:
            if stream_id in self.frame_buffers and self.frame_buffers[stream_id]:
                frame_data = self.frame_buffers[stream_id][-1]
                if frame_data and len(frame_data) > 0:
                    return frame_data
                else:
                    logger.warning(f"⚠️ Empty frame data for {stream_id}")
                    return None
            else:
                logger.warning(f"⚠️ No frame buffer for {stream_id}")
                # Create buffer lazily to avoid repeated warnings
                self.frame_buffers[stream_id] = []
            return None
        except Exception as e:
            logger.error(f"❌ Get frame error for {stream_id}: {e}")
            return None
    
    def get_stream_status(self, stream_id: str) -> Optional[Dict]:
        """Get stream status"""
        try:
            if stream_id in self.active_streams:
                return self.active_streams[stream_id]
            return None
        except Exception as e:
            logger.error(f"❌ Get status error: {e}")
            return None
    
    def _perform_ppe_detection(self, frame, stream_id: str) -> Dict:
        """Perform PPE detection on a frame"""
        try:
            # SH17 Model Manager'ı başlat
            from src.smartsafe.models.sh17_model_manager import SH17ModelManager
            sh17_manager = SH17ModelManager()
            
            # Stream info'dan sector bilgisini al (varsayılan: construction)
            sector = 'construction'  # Varsayılan sektör
            if stream_id in self.active_streams:
                # Stream ID'den sector çıkar (örn: DVR_192_168_1_114_1 -> construction)
                if 'construction' in stream_id.lower():
                    sector = 'construction'
                elif 'manufacturing' in stream_id.lower():
                    sector = 'manufacturing'
                elif 'chemical' in stream_id.lower():
                    sector = 'chemical'
                elif 'food' in stream_id.lower():
                    sector = 'food_beverage'
                elif 'warehouse' in stream_id.lower():
                    sector = 'warehouse_logistics'
                elif 'energy' in stream_id.lower():
                    sector = 'energy'
                elif 'petrochemical' in stream_id.lower():
                    sector = 'petrochemical'
                elif 'marine' in stream_id.lower():
                    sector = 'marine_shipyard'
                elif 'aviation' in stream_id.lower():
                    sector = 'aviation'
            
            # 🎯 PPE detection yap - PRODUCTION-GRADE (lowered confidence threshold)
            detections = sh17_manager.detect_ppe(frame, sector=sector, confidence=0.25)
            
            # Detection result'ı hazırla - String değil Dict olarak döndür
            people_detected = len([d for d in detections if isinstance(d, dict) and d.get('class_name') == 'person'])
            
            # Compliance analizi
            required_ppe = sh17_manager.get_sector_requirements(sector)
            compliance_analysis = sh17_manager.analyze_compliance(detections, required_ppe)
            
            detection_result = {
                'detections': detections if isinstance(detections, list) else [],
                'people_detected': people_detected,
                'compliance_rate': int(compliance_analysis.get('score', 0) * 100) if isinstance(compliance_analysis, dict) else 100,
                'ppe_violations': compliance_analysis.get('missing', []) if isinstance(compliance_analysis, dict) else [],
                'timestamp': time.time(),
                'sector': sector,
                'model_type': 'SH17' if sh17_manager.is_sh17_available(sector) else 'Fallback'
            }
            
            return detection_result
            
        except Exception as e:
            logger.error(f"❌ PPE Detection error: {e}")
            # Hata durumunda boş result döndür
            return {
                'detections': [],
                'people_detected': 0,
                'compliance_rate': 100,
                'ppe_violations': [],
                'timestamp': time.time(),
                'sector': 'unknown',
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
        urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
        # Try a very small subset first for speed (most likely to work)
        candidates = urls[:4]
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
                    self.active_streams[stream_id]['status'] = 'error'
                    return
            
            # Generate multiple URLs to try
            urls_to_try = [rtsp_url]  # Start with original URL
            
            # Add brand-specific URLs if we have the parameters
            if all([ip_address, username, password, rtsp_port, channel_number]):
                brand_urls = self.generate_rtsp_urls(ip_address, username, password, rtsp_port, channel_number)
                urls_to_try.extend(brand_urls)
                logger.info(f"🎯 Channel {channel_number}: Will try {len(urls_to_try)} different URL patterns")
            else:
                logger.warning(f"⚠️ Channel {channel_number}: Missing parameters for enhanced URL generation")
            
            # Try each URL, prioritize Hikvision ISAPI channels if present
            cap = None
            successful_url = None
            
            # Prioritize vendor-specific working URLs: XM stream.sdp first, then cam/realmonitor,
            # then ISAPI, then /chXX/main and others
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
                    
                    cap = cv2.VideoCapture(url)
                    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.connection_timeout)
                    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout)
                    
                    if cap.isOpened():
                        # Test if we can actually read a frame
                        ret, test_frame = cap.read()
                        if ret and test_frame is not None:
                            logger.info(f"✅ Channel {channel_number}: Successfully opened RTSP stream: {url}")
                            successful_url = url
                            break
                        else:
                            logger.warning(f"⚠️ Channel {channel_number}: Failed to open URL: {url}")
                            if cap:
                                cap.release()
                                cap = None
                            else:
                                logger.warning(f"⚠️ Channel {channel_number}: URL opened but no frame data: {url}")
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
                self.active_streams[stream_id]['status'] = 'error'
                return
            
            # Update stream info with successful URL
            self.active_streams[stream_id]['rtsp_url'] = successful_url
            self.active_streams[stream_id]['status'] = 'active'
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
                                        cap = cv2.VideoCapture(url)
                                        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.connection_timeout)
                                        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout)
                                        
                                        if cap.isOpened():
                                            ret, test_frame = cap.read()
                                            if ret and test_frame is not None:
                                                logger.info(f"✅ Channel {channel_number}: Reconnection successful: {url}")
                                                successful_url = url
                                                consecutive_errors = 0
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
                                self.active_streams[stream_id]['status'] = 'error'
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
                                # SH17 Model Manager'ı import et
                                from src.smartsafe.models.sh17_model_manager import SH17ModelManager
                                
                                # Detection yap
                                detection_result = self._perform_ppe_detection(frame, stream_id)
                                
                                # Stream info'ya detection result'ı ekle
                                if stream_id in self.active_streams:
                                    self.active_streams[stream_id]['detection_result'] = detection_result
                                    
                                logger.info(f"🎯 {stream_id}: Detection completed - People: {detection_result.get('people_detected', 0)}, PPE: {len(detection_result.get('detections', []))}")
                                
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
                self.active_streams[stream_id]['status'] = 'error'
        finally:
            if cap:
                cap.release()
            if stream_id in self.active_streams:
                self.active_streams[stream_id]['status'] = 'stopped'
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

def get_stream_handler() -> DVRStreamHandler:
    """Get global stream handler instance"""
    return stream_handler 