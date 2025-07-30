#!/usr/bin/env python3
"""
SmartSafe AI - Professional Camera Integration Manager
Enterprise-grade camera management with IP Webcam, RTSP, and real camera support
"""

import cv2
import numpy as np
import requests
import socket
import threading
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import base64
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class RealCameraConfig:
    """Real camera configuration based on actual camera settings"""
    camera_id: str
    name: str
    ip_address: str
    port: int = 8080
    username: str = ""
    password: str = ""
    protocol: str = "http"  # http, rtsp, onvif
    stream_path: str = "/video"
    auth_type: str = "basic"  # basic, digest, none
    resolution: Tuple[int, int] = (1920, 1080)
    fps: int = 25
    quality: int = 80
    audio_enabled: bool = False
    night_vision: bool = False
    motion_detection: bool = True
    recording_enabled: bool = True
    status: str = "inactive"  # active, inactive, error, testing
    last_test_time: Optional[datetime] = None
    connection_retries: int = 3
    timeout: int = 10
    
    def get_stream_url(self) -> str:
        """Generate stream URL based on configuration"""
        if self.protocol == "rtsp":
            if self.username and self.password:
                return f"rtsp://{self.username}:{self.password}@{self.ip_address}:{self.port}{self.stream_path}"
            else:
                return f"rtsp://{self.ip_address}:{self.port}{self.stream_path}"
        else:  # HTTP
            return f"http://{self.ip_address}:{self.port}{self.stream_path}"
    
    def get_mjpeg_url(self) -> str:
        """Generate MJPEG snapshot URL"""
        return f"http://{self.ip_address}:{self.port}/shot.jpg"
    
    def get_auth_header(self) -> Dict[str, str]:
        """Generate authentication header"""
        if self.auth_type == "basic" and self.username and self.password:
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            return {"Authorization": f"Basic {credentials}"}
        return {}

@dataclass
class CameraSource:
    """Professional camera source configuration"""
    camera_id: str
    name: str
    source_type: str  # 'real_camera', 'ip_webcam', 'rtsp', 'local', 'usb'
    connection_url: str
    backup_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    resolution: Tuple[int, int] = (1280, 720)
    fps: int = 25
    timeout: int = 10
    retry_attempts: int = 3
    enabled: bool = True
    last_connection_test: Optional[datetime] = None
    connection_status: str = "unknown"  # unknown, connected, failed, testing

class RealCameraManager:
    """Enhanced real camera management system"""
    
    def __init__(self):
        self.real_cameras: Dict[str, RealCameraConfig] = {}
        self.active_streams: Dict[str, cv2.VideoCapture] = {}
        self.connection_threads: Dict[str, threading.Thread] = {}
        self.frame_buffers: Dict[str, np.ndarray] = {}
        self.last_frames: Dict[str, datetime] = {}
        
        # Performance tracking
        self.fps_counters: Dict[str, List[float]] = {}
        self.connection_stats: Dict[str, Dict] = {}
        
        logger.info("🎥 Real Camera Manager initialized")
    
    def add_real_camera(self, camera_config: RealCameraConfig) -> Tuple[bool, str]:
        """Add a real camera to the system"""
        try:
            # Test connection first
            test_result = self.test_real_camera_connection(camera_config)
            
            if test_result['success']:
                self.real_cameras[camera_config.camera_id] = camera_config
                camera_config.status = "active"
                camera_config.last_test_time = datetime.now()
                
                logger.info(f"✅ Real camera added successfully: {camera_config.name}")
                return True, "Camera added successfully"
            else:
                logger.error(f"❌ Failed to add camera: {test_result['error']}")
                return False, test_result['error']
                
        except Exception as e:
            logger.error(f"❌ Error adding real camera: {e}")
            return False, str(e)
    
    def test_real_camera_connection(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test real camera connection with comprehensive checks"""
        logger.info(f"🔍 Testing real camera connection: {camera_config.name}")
        
        result = {
            'success': False,
            'error': '',
            'connection_time': 0,
            'stream_quality': 'unknown',
            'supported_features': [],
            'camera_info': {}
        }
        
        start_time = time.time()
        
        try:
            # 1. Basic connectivity test
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(camera_config.timeout)
            
            connection_result = sock.connect_ex((camera_config.ip_address, camera_config.port))
            sock.close()
            
            if connection_result != 0:
                result['error'] = f"Cannot connect to {camera_config.ip_address}:{camera_config.port}"
                return result
            
            # 2. HTTP/RTSP stream test
            if camera_config.protocol == "rtsp":
                stream_test = self._test_rtsp_stream(camera_config)
            else:
                stream_test = self._test_http_stream(camera_config)
            
            if not stream_test['success']:
                result['error'] = stream_test['error']
                return result
            
            # 3. Authentication test
            if camera_config.username and camera_config.password:
                auth_test = self._test_camera_authentication(camera_config)
                if not auth_test['success']:
                    result['error'] = f"Authentication failed: {auth_test['error']}"
                    return result
            
            # 4. Feature detection
            features = self._detect_camera_features(camera_config)
            result['supported_features'] = features
            
            # 5. Quality assessment
            quality_info = self._assess_stream_quality(camera_config)
            result['stream_quality'] = quality_info
            
            result['connection_time'] = time.time() - start_time
            result['success'] = True
            
            logger.info(f"✅ Camera connection test passed: {camera_config.name}")
            return result
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Camera connection test failed: {e}")
            return result
    
    def _test_http_stream(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test HTTP stream connection"""
        try:
            stream_url = camera_config.get_stream_url()
            headers = camera_config.get_auth_header()
            
            # Test MJPEG snapshot first
            mjpeg_url = camera_config.get_mjpeg_url()
            response = requests.get(mjpeg_url, headers=headers, timeout=camera_config.timeout)
            
            if response.status_code == 200:
                # Try to open video stream
                cap = cv2.VideoCapture(stream_url)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret and frame is not None:
                        return {'success': True, 'frame_size': frame.shape}
                    else:
                        return {'success': False, 'error': 'No frame received'}
                else:
                    return {'success': False, 'error': 'Cannot open video stream'}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_rtsp_stream(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test RTSP stream connection"""
        try:
            stream_url = camera_config.get_stream_url()
            
            cap = cv2.VideoCapture(stream_url)
            if cap.isOpened():
                # Set timeout
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                ret, frame = cap.read()
                cap.release()
                
                if ret and frame is not None:
                    return {'success': True, 'frame_size': frame.shape}
                else:
                    return {'success': False, 'error': 'No frame received from RTSP'}
            else:
                return {'success': False, 'error': 'Cannot open RTSP stream'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _test_camera_authentication(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Test camera authentication"""
        try:
            test_url = f"http://{camera_config.ip_address}:{camera_config.port}/status"
            headers = camera_config.get_auth_header()
            
            response = requests.get(test_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                return {'success': True}
            elif response.status_code == 401:
                return {'success': False, 'error': 'Invalid credentials'}
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _detect_camera_features(self, camera_config: RealCameraConfig) -> List[str]:
        """Detect available camera features"""
        features = []
        
        try:
            # Test common endpoints
            base_url = f"http://{camera_config.ip_address}:{camera_config.port}"
            headers = camera_config.get_auth_header()
            
            # Common feature endpoints
            feature_endpoints = {
                'ptz': '/ptz',
                'zoom': '/zoom',
                'focus': '/focus',
                'night_vision': '/night_vision',
                'motion_detection': '/motion',
                'audio': '/audio',
                'recording': '/recording'
            }
            
            for feature, endpoint in feature_endpoints.items():
                try:
                    response = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=2)
                    if response.status_code == 200:
                        features.append(feature)
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"Feature detection error: {e}")
        
        return features
    
    def _assess_stream_quality(self, camera_config: RealCameraConfig) -> Dict[str, Any]:
        """Assess stream quality"""
        try:
            stream_url = camera_config.get_stream_url()
            cap = cv2.VideoCapture(stream_url)
            
            if cap.isOpened():
                # Get actual resolution
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                
                cap.release()
                
                return {
                    'resolution': f"{width}x{height}",
                    'fps': fps,
                    'quality': 'good' if width >= 1280 else 'medium'
                }
            else:
                return {'quality': 'unknown', 'error': 'Cannot open stream'}
                
        except Exception as e:
            return {'quality': 'unknown', 'error': str(e)}
    
    def get_real_camera_status(self, camera_id: str) -> Dict[str, Any]:
        """Get comprehensive real camera status"""
        if camera_id not in self.real_cameras:
            return {'status': 'not_found'}
        
        camera = self.real_cameras[camera_id]
        
        return {
            'camera_id': camera_id,
            'name': camera.name,
            'ip_address': camera.ip_address,
            'port': camera.port,
            'protocol': camera.protocol,
            'status': camera.status,
            'resolution': f"{camera.resolution[0]}x{camera.resolution[1]}",
            'fps': camera.fps,
            'quality': camera.quality,
            'audio_enabled': camera.audio_enabled,
            'night_vision': camera.night_vision,
            'motion_detection': camera.motion_detection,
            'recording_enabled': camera.recording_enabled,
            'last_test_time': camera.last_test_time,
            'stream_url': camera.get_stream_url(),
            'mjpeg_url': camera.get_mjpeg_url()
        }
    
    def create_real_camera_from_form(self, form_data: Dict[str, Any]) -> RealCameraConfig:
        """Create real camera configuration from form data"""
        import uuid
        
        camera_id = form_data.get('camera_id', str(uuid.uuid4()))
        
        return RealCameraConfig(
            camera_id=camera_id,
            name=form_data.get('name', 'Real Camera'),
            ip_address=form_data.get('ip_address', '192.168.1.100'),
            port=int(form_data.get('port', 8080)),
            username=form_data.get('username', ''),
            password=form_data.get('password', ''),
            protocol=form_data.get('protocol', 'http'),
            stream_path=form_data.get('stream_path', '/video'),
            auth_type=form_data.get('auth_type', 'basic'),
            resolution=(
                int(form_data.get('width', 1920)),
                int(form_data.get('height', 1080))
            ),
            fps=int(form_data.get('fps', 25)),
            quality=int(form_data.get('quality', 80)),
            audio_enabled=form_data.get('audio_enabled', False),
            night_vision=form_data.get('night_vision', False),
            motion_detection=form_data.get('motion_detection', True),
            recording_enabled=form_data.get('recording_enabled', True)
        )

class SmartCameraDetector:
    """Akıllı kamera tespit sistemi - Yeni eklenen sınıf"""
    
    def __init__(self):
        # Genişletilmiş kamera modeli veritabanı
        self.camera_database = {
            'hikvision': {
                'name': 'Hikvision',
                'ports': [554, 80, 8000, 8080, 443],
                'paths': ['/Streaming/Channels/101', '/ISAPI/Streaming/channels/101', '/doc/page/login.asp'],
                'headers': ['Server: App-webs/', 'Server: uc-httpd'],
                'default_rtsp': 'rtsp://{ip}:554/Streaming/Channels/101',
                'default_http': 'http://{ip}:80/ISAPI/Streaming/channels/101',
                'auth_endpoints': ['/ISAPI/System/deviceInfo', '/doc/page/login.asp']
            },
            'dahua': {
                'name': 'Dahua',
                'ports': [554, 80, 37777, 443],
                'paths': ['/cam/realmonitor?channel=1&subtype=0', '/cgi-bin/magicBox.cgi'],
                'headers': ['Server: DahuaHttp'],
                'default_rtsp': 'rtsp://{ip}:554/cam/realmonitor?channel=1&subtype=0',
                'default_http': 'http://{ip}:80/cgi-bin/magicBox.cgi',
                'auth_endpoints': ['/cgi-bin/magicBox.cgi?action=getDeviceType']
            },
            'axis': {
                'name': 'Axis',
                'ports': [554, 80, 443],
                'paths': ['/axis-media/media.amp', '/axis-cgi/jpg/image.cgi'],
                'headers': ['Server: axis'],
                'default_rtsp': 'rtsp://{ip}:554/axis-media/media.amp',
                'default_http': 'http://{ip}:80/axis-cgi/jpg/image.cgi',
                'auth_endpoints': ['/axis-cgi/param.cgi?action=list']
            },
            'foscam': {
                'name': 'Foscam',
                'ports': [554, 88, 80],
                'paths': ['/videoMain', '/videostream.cgi'],
                'headers': ['Server: Foscam'],
                'default_rtsp': 'rtsp://{ip}:554/videoMain',
                'default_http': 'http://{ip}:88/videostream.cgi',
                'auth_endpoints': ['/cgi-bin/CGIProxy.fcgi?cmd=getDevState']
            },
            'generic_ip': {
                'name': 'Generic IP Camera',
                'ports': [554, 8080, 80, 8000],
                'paths': ['/video', '/stream', '/mjpeg', '/shot.jpg', '/live'],
                'headers': [],
                'default_rtsp': 'rtsp://{ip}:554/stream',
                'default_http': 'http://{ip}:8080/video',
                'auth_endpoints': ['/status', '/info']
            },
            'android_ipwebcam': {
                'name': 'Android IP Webcam',
                'ports': [8080, 8081, 8082],
                'paths': ['/shot.jpg', '/video', '/mjpeg'],
                'headers': ['Server: IP Webcam'],
                'default_rtsp': 'rtsp://{ip}:8080/video',
                'default_http': 'http://{ip}:8080/shot.jpg',
                'auth_endpoints': ['/settings']
            }
        }
        
        # Yaygın port ve path kombinasyonları
        self.common_combinations = [
            {'port': 80, 'path': '/video', 'protocol': 'http'},
            {'port': 80, 'path': '/stream', 'protocol': 'http'},
            {'port': 80, 'path': '/mjpeg', 'protocol': 'http'},
            {'port': 8080, 'path': '/video', 'protocol': 'http'},
            {'port': 8080, 'path': '/shot.jpg', 'protocol': 'http'},
            {'port': 554, 'path': '/stream', 'protocol': 'rtsp'},
            {'port': 554, 'path': '/video', 'protocol': 'rtsp'},
            {'port': 554, 'path': '/live', 'protocol': 'rtsp'},
            {'port': 8000, 'path': '/video', 'protocol': 'http'},
            {'port': 8000, 'path': '/stream', 'protocol': 'http'}
        ]
    
    def smart_detect_camera(self, ip_address: str, timeout: int = 3) -> Dict[str, Any]:
        """
        Akıllı kamera tespiti - Basitleştirilmiş versiyon
        
        Args:
            ip_address: Kamera IP adresi
            timeout: Bağlantı zaman aşımı
            
        Returns:
            Tespit edilen kamera bilgileri
        """
        logger.info(f"🔍 Smart camera detection started for {ip_address}")
        
        result = {
            'success': False,
            'ip_address': ip_address,
            'detected_model': 'unknown',
            'protocol': None,
            'port': None,
            'path': None,
            'stream_url': None,
            'mjpeg_url': None,
            'auth_required': False,
            'detection_confidence': 0.0,
            'error': None
        }
        
        try:
            # 1. Ping testi
            if not self._ping_test(ip_address):
                result['error'] = "IP adresi erişilebilir değil"
                return result
            
            # 2. Basit konfigürasyon tespiti (model tespiti olmadan)
            logger.info(f"🔍 Quick configuration detection for {ip_address}")
            
            # 8080 portu için Android IP Webcam varsayılanı
            if self._test_http_stream(f"http://{ip_address}:8080/shot.jpg", 2):
                result.update({
                    'success': True,
                    'detected_model': 'android_ipwebcam',
                    'protocol': 'http',
                    'port': 8080,
                    'path': '/shot.jpg',
                    'stream_url': f"http://{ip_address}:8080/shot.jpg",
                    'mjpeg_url': f"http://{ip_address}:8080/shot.jpg",
                    'detection_confidence': 0.8
                })
                logger.info(f"✅ Quick detection successful: Android IP Webcam on port 8080")
                return result
            
            # 8080 portu için video endpoint
            if self._test_http_stream(f"http://{ip_address}:8080/video", 2):
                result.update({
                    'success': True,
                    'detected_model': 'generic_ip',
                    'protocol': 'http',
                    'port': 8080,
                    'path': '/video',
                    'stream_url': f"http://{ip_address}:8080/video",
                    'mjpeg_url': f"http://{ip_address}:8080/shot.jpg",
                    'detection_confidence': 0.7
                })
                logger.info(f"✅ Quick detection successful: Generic IP Camera on port 8080")
                return result
            
            # 80 portu için test
            if self._test_http_stream(f"http://{ip_address}:80/video", 2):
                result.update({
                    'success': True,
                    'detected_model': 'generic_ip',
                    'protocol': 'http',
                    'port': 80,
                    'path': '/video',
                    'stream_url': f"http://{ip_address}:80/video",
                    'mjpeg_url': f"http://{ip_address}:80/shot.jpg",
                    'detection_confidence': 0.7
                })
                logger.info(f"✅ Quick detection successful: Generic IP Camera on port 80")
                return result
            
            result['error'] = "Çalışan kamera konfigürasyonu bulunamadı"
            logger.warning(f"❌ Quick detection failed for {ip_address}")
            return result
            
        except Exception as e:
            result['error'] = f"Tespit hatası: {str(e)}"
            logger.error(f"❌ Smart detection failed for {ip_address}: {e}")
            return result
    
    def _ping_test(self, ip_address: str) -> bool:
        """Ping testi - Yaygın portları test et"""
        common_ports = [80, 8080, 554, 8000, 443]
        
        for port in common_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((ip_address, port))
                sock.close()
                if result == 0:
                    logger.info(f"✅ Ping test başarılı: {ip_address}:{port}")
                    return True
            except:
                continue
        
        logger.warning(f"❌ Ping test başarısız: {ip_address} - Hiçbir port açık değil")
        return False
    
    def _detect_camera_model(self, ip_address: str, timeout: int) -> Optional[Dict]:
        """Kamera modelini tespit et - Hızlandırılmış versiyon"""
        logger.info(f"🔍 Model detection started for {ip_address}")
        
        # Hızlı test için sadece yaygın portları test et
        quick_ports = [8080, 80, 554]
        
        for port in quick_ports:
            try:
                # Basit HTTP testi
                url = f"http://{ip_address}:{port}/"
                response = requests.get(url, timeout=2)  # 2 saniye timeout
                
                if response.status_code == 200:
                    content = response.text.lower()
                    headers = str(response.headers).lower()
                    
                    # Android IP Webcam tespiti (en yaygın)
                    if 'ip webcam' in content or 'ipwebcam' in content or 'android' in content:
                        logger.info(f"✅ Android IP Webcam detected on port {port}")
                        return {
                            'model': 'android_ipwebcam',
                            'confidence': 0.9,
                            'info': self.camera_database['android_ipwebcam']
                        }
                    
                    # Hikvision tespiti
                    if 'hikvision' in content or 'app-webs' in headers:
                        logger.info(f"✅ Hikvision detected on port {port}")
                        return {
                            'model': 'hikvision',
                            'confidence': 0.9,
                            'info': self.camera_database['hikvision']
                        }
                    
                    # Dahua tespiti
                    if 'dahua' in content or 'dahuahttp' in headers:
                        logger.info(f"✅ Dahua detected on port {port}")
                        return {
                            'model': 'dahua',
                            'confidence': 0.9,
                            'info': self.camera_database['dahua']
                        }
                    
                    # Generic IP Camera (varsayılan)
                    logger.info(f"✅ Generic IP Camera detected on port {port}")
                    return {
                        'model': 'generic_ip',
                        'confidence': 0.7,
                        'info': self.camera_database['generic_ip']
                    }
                    
            except Exception as e:
                logger.debug(f"❌ Port {port} test failed: {e}")
                continue
        
        logger.warning(f"❌ No camera model detected for {ip_address}")
        return None
    
    def _find_working_config(self, ip_address: str, model_info: Optional[Dict], timeout: int) -> Optional[Dict]:
        """Çalışan konfigürasyonu bul"""
        # Önce model bilgisine göre test et
        if model_info:
            config = self._test_model_config(ip_address, model_info, timeout)
            if config:
                return config
        
        # Genel kombinasyonları test et
        for combo in self.common_combinations:
            config = self._test_combination(ip_address, combo, timeout)
            if config:
                return config
        
        return None
    
    def _test_model_config(self, ip_address: str, model_info: Dict, timeout: int) -> Optional[Dict]:
        """Model bilgisine göre konfigürasyon test et"""
        info = model_info['info']
        
        # RTSP testleri
        for port in info['ports']:
            if port == 554:  # RTSP portu
                for path in info['paths']:
                    if 'rtsp' in path or 'stream' in path:
                        rtsp_url = f"rtsp://{ip_address}:{port}{path}"
                        if self._test_rtsp_stream(rtsp_url, timeout):
                            return {
                                'protocol': 'rtsp',
                                'port': port,
                                'path': path,
                                'stream_url': rtsp_url,
                                'mjpeg_url': f"http://{ip_address}:80/shot.jpg"
                            }
        
        # HTTP testleri
        for port in info['ports']:
            if port in [80, 8080, 8000]:  # HTTP portları
                for path in info['paths']:
                    http_url = f"http://{ip_address}:{port}{path}"
                    if self._test_http_stream(http_url, timeout):
                        return {
                            'protocol': 'http',
                            'port': port,
                            'path': path,
                            'stream_url': http_url,
                            'mjpeg_url': f"http://{ip_address}:{port}/shot.jpg"
                        }
        
        return None
    
    def _test_combination(self, ip_address: str, combo: Dict, timeout: int) -> Optional[Dict]:
        """Kombinasyon test et"""
        if combo['protocol'] == 'rtsp':
            rtsp_url = f"rtsp://{ip_address}:{combo['port']}{combo['path']}"
            if self._test_rtsp_stream(rtsp_url, timeout):
                return {
                    'protocol': 'rtsp',
                    'port': combo['port'],
                    'path': combo['path'],
                    'stream_url': rtsp_url,
                    'mjpeg_url': f"http://{ip_address}:80/shot.jpg"
                }
        else:
            http_url = f"http://{ip_address}:{combo['port']}{combo['path']}"
            if self._test_http_stream(http_url, timeout):
                return {
                    'protocol': 'http',
                    'port': combo['port'],
                    'path': combo['path'],
                    'stream_url': http_url,
                    'mjpeg_url': f"http://{ip_address}:{combo['port']}/shot.jpg"
                }
        
        return None
    
    def _test_rtsp_stream(self, rtsp_url: str, timeout: int) -> bool:
        """RTSP stream test et"""
        try:
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Kısa süreli test
            start_time = time.time()
            while time.time() - start_time < timeout:
                ret, frame = cap.read()
                if ret and frame is not None:
                    cap.release()
                    return True
                time.sleep(0.1)
            
            cap.release()
            return False
        except:
            return False
    
    def _test_http_stream(self, http_url: str, timeout: int) -> bool:
        """HTTP stream test et - Basitleştirilmiş versiyon"""
        try:
            logger.debug(f"🔍 Testing HTTP stream: {http_url}")
            response = requests.get(http_url, timeout=timeout)
            
            # 200, 401, 403 gibi status kodları kabul et (authentication gerekebilir)
            if response.status_code in [200, 401, 403]:
                logger.debug(f"✅ HTTP stream test successful: {http_url} (Status: {response.status_code})")
                return True
            
            logger.debug(f"❌ HTTP stream test failed: {http_url} (Status: {response.status_code})")
            return False
        except Exception as e:
            logger.debug(f"❌ HTTP stream test error: {http_url} - {e}")
            return False

class ProfessionalCameraManager:
    """Enterprise-grade camera management system"""
    
    def __init__(self):
        self.active_cameras: Dict[str, cv2.VideoCapture] = {}
        self.camera_configs: Dict[str, CameraSource] = {}
        self.connection_threads: Dict[str, threading.Thread] = {}
        self.frame_buffers: Dict[str, np.ndarray] = {}
        self.last_frames: Dict[str, datetime] = {}
        
        # Performance tracking
        self.fps_counters: Dict[str, List[float]] = {}
        self.connection_stats: Dict[str, Dict] = {}
        
        logger.info("🎥 Professional Camera Manager initialized")
    
    def detect_ip_webcam_cameras(self, network_range: str = "192.168.1.0/24") -> List[Dict]:
        """Detect IP Webcam apps on network"""
        logger.info(f"🔍 Scanning for IP Webcam cameras on {network_range}")
        
        discovered_cameras = []
        
        try:
            import ipaddress
            network = ipaddress.IPv4Network(network_range, strict=False)
            
            def test_ip_webcam(ip: str):
                """Test if IP has IP Webcam running"""
                try:
                    # Common IP Webcam ports
                    for port in [8080, 8081, 8888]:
                        test_url = f"http://{ip}:{port}"
                        response = requests.get(test_url, timeout=2)
                        
                        if response.status_code == 200:
                            # Check if it's IP Webcam
                            if 'IP Webcam' in response.text or 'video' in response.text.lower():
                                camera_info = {
                                    'ip': ip,
                                    'port': port,
                                    'type': 'ip_webcam',
                                    'video_url': f"{test_url}/video",
                                    'mjpeg_url': f"{test_url}/shot.jpg",
                                    'status': 'detected'
                                }
                                discovered_cameras.append(camera_info)
                                logger.info(f"📱 IP Webcam found: {ip}:{port}")
                                return
                except:
                    pass
            
            # Test first 20 IPs for speed
            test_ips = list(network.hosts())[:20]
            threads = []
            
            for ip in test_ips:
                thread = threading.Thread(target=test_ip_webcam, args=(str(ip),))
                thread.start()
                threads.append(thread)
            
            # Wait for all threads with timeout
            for thread in threads:
                thread.join(timeout=5)
            
            logger.info(f"✅ IP Webcam scan complete: {len(discovered_cameras)} cameras found")
            return discovered_cameras
            
        except Exception as e:
            logger.error(f"❌ IP Webcam detection failed: {e}")
            return []
    
    def test_camera_connection(self, camera_config: CameraSource) -> Dict[str, Any]:
        """Professional camera connection testing"""
        logger.info(f"🧪 Testing camera connection: {camera_config.name}")
        
        test_result = {
            'camera_id': camera_config.camera_id,
            'name': camera_config.name,
            'source_type': camera_config.source_type,
            'connection_status': 'failed',
            'response_time_ms': None,
            'resolution_detected': None,
            'fps_detected': None,
            'error_message': None,
            'test_timestamp': datetime.now(),
            'features': {
                'video_stream': False,
                'mjpeg_support': False,
                'rtsp_support': False
            }
        }
        
        start_time = time.time()
        
        try:
            if camera_config.source_type == 'ip_webcam':
                # Test IP Webcam connection
                test_result.update(self._test_ip_webcam(camera_config))
                
            elif camera_config.source_type == 'rtsp':
                # Test RTSP connection
                test_result.update(self._test_rtsp_connection(camera_config))
                
            elif camera_config.source_type == 'local':
                # Test local camera
                test_result.update(self._test_local_camera(camera_config))
                
            elif camera_config.source_type == 'usb':
                # Test USB camera
                test_result.update(self._test_usb_camera(camera_config))
            
            # Calculate response time
            test_result['response_time_ms'] = (time.time() - start_time) * 1000
            
            # Update camera config
            camera_config.last_connection_test = datetime.now()
            camera_config.connection_status = test_result['connection_status']
            
            # Success kontrolü ekle
            if test_result['connection_status'] == 'connected':
                test_result['success'] = True
            else:
                test_result['success'] = False
            
            logger.info(f"✅ Camera test complete: {camera_config.name} - {test_result['connection_status']}")
            
        except Exception as e:
            test_result['error_message'] = str(e)
            test_result['connection_status'] = 'failed'
            test_result['success'] = False
            logger.error(f"❌ Camera test failed: {camera_config.name} - {e}")
        
        return test_result
    
    def _test_ip_webcam(self, config: CameraSource) -> Dict:
        """Test IP Webcam specific connection"""
        result = {}
        
        try:
            # Authentication header'ı ekle
            headers = {}
            if config.username and config.password:
                import base64
                credentials = base64.b64encode(f"{config.username}:{config.password}".encode()).decode()
                headers['Authorization'] = f'Basic {credentials}'
            
            # Test basic HTTP connection with authentication
            response = requests.get(config.connection_url, headers=headers, timeout=config.timeout)
            if response.status_code == 200:
                result['features']['mjpeg_support'] = True
                
                # Test video stream with authentication
                video_url = config.connection_url.replace('/shot.jpg', '/video')
                cap = cv2.VideoCapture(video_url)
                
                # Authentication için URL'yi güncelle
                if config.username and config.password:
                    if 'http://' in video_url:
                        video_url = video_url.replace('http://', f'http://{config.username}:{config.password}@')
                    elif 'https://' in video_url:
                        video_url = video_url.replace('https://', f'https://{config.username}:{config.password}@')
                
                cap = cv2.VideoCapture(video_url)
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        result['connection_status'] = 'connected'
                        result['features']['video_stream'] = True
                        result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                        
                        # Test FPS
                        fps_start = time.time()
                        frame_count = 0
                        while frame_count < 10 and (time.time() - fps_start) < 2:
                            ret, _ = cap.read()
                            if ret:
                                frame_count += 1
                        
                        if frame_count > 0:
                            elapsed = time.time() - fps_start
                            result['fps_detected'] = round(frame_count / elapsed, 1)
                    
                    cap.release()
                else:
                    result['connection_status'] = 'failed'
                    result['error_message'] = 'Could not open video stream'
            else:
                result['connection_status'] = 'failed'
                result['error_message'] = f'HTTP {response.status_code}'
                
        except Exception as e:
            result['connection_status'] = 'failed'
            error_msg = str(e)
            
            # Detaylı hata mesajları
            if 'timeout' in error_msg.lower():
                result['error_message'] = 'Bağlantı zaman aşımı. IP adresi ve port numarasını kontrol edin.'
            elif 'connection refused' in error_msg.lower():
                result['error_message'] = 'Bağlantı reddedildi. Kamera açık mı ve port doğru mu?'
            elif 'no route to host' in error_msg.lower():
                result['error_message'] = 'IP adresine ulaşılamıyor. Ağ bağlantısını kontrol edin.'
            elif 'name or service not known' in error_msg.lower():
                result['error_message'] = 'Geçersiz IP adresi formatı.'
            elif 'authentication' in error_msg.lower():
                result['error_message'] = 'Kimlik doğrulama hatası. Kullanıcı adı ve şifreyi kontrol edin.'
            elif '404' in error_msg.lower():
                result['error_message'] = 'Stream path bulunamadı. Farklı endpoint deneyin (/video, /shot.jpg).'
            elif '403' in error_msg.lower():
                result['error_message'] = 'Erişim reddedildi. Yetkilendirme gerekli.'
            elif '401' in error_msg.lower():
                result['error_message'] = 'Kimlik doğrulama gerekli. Kullanıcı adı ve şifreyi kontrol edin.'
            else:
                result['error_message'] = f'Bağlantı hatası: {error_msg}'
        
        return result
    
    def _test_rtsp_connection(self, config: CameraSource) -> Dict:
        """Test RTSP connection"""
        result = {}
        
        try:
            cap = cv2.VideoCapture(config.connection_url)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    result['connection_status'] = 'connected'
                    result['features']['rtsp_support'] = True
                    result['features']['video_stream'] = True
                    result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                else:
                    result['connection_status'] = 'failed'
                    result['error_message'] = 'No frames received'
                
                cap.release()
            else:
                result['connection_status'] = 'failed'
                result['error_message'] = 'Could not open RTSP stream'
                
        except Exception as e:
            result['connection_status'] = 'failed'
            result['error_message'] = str(e)
        
        return result
    
    def _test_local_camera(self, config: CameraSource) -> Dict:
        """Test local/laptop camera"""
        result = {}
        
        try:
            camera_index = int(config.connection_url)
            cap = cv2.VideoCapture(camera_index)
            
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    result['connection_status'] = 'connected'
                    result['features']['video_stream'] = True
                    result['resolution_detected'] = f"{frame.shape[1]}x{frame.shape[0]}"
                    result['fps_detected'] = cap.get(cv2.CAP_PROP_FPS)
                else:
                    result['connection_status'] = 'failed'
                    result['error_message'] = 'No frames from local camera'
                
                cap.release()
            else:
                result['connection_status'] = 'failed'
                result['error_message'] = 'Could not open local camera'
                
        except Exception as e:
            result['connection_status'] = 'failed'
            result['error_message'] = str(e)
        
        return result
    
    def _test_usb_camera(self, config: CameraSource) -> Dict:
        """Test USB camera connection"""
        return self._test_local_camera(config)  # Same logic as local camera
    
    def connect_camera(self, camera_config: CameraSource) -> bool:
        """Connect to camera with professional error handling"""
        logger.info(f"🔌 Connecting to camera: {camera_config.name}")
        
        try:
            # Test connection first
            test_result = self.test_camera_connection(camera_config)
            
            if test_result['connection_status'] != 'connected':
                logger.error(f"❌ Connection test failed: {camera_config.name}")
                return False
            
            # Create video capture
            if camera_config.source_type == 'ip_webcam':
                video_url = camera_config.connection_url.replace('/shot.jpg', '/video')
                cap = cv2.VideoCapture(video_url)
            else:
                cap = cv2.VideoCapture(camera_config.connection_url)
            
            if not cap.isOpened():
                logger.error(f"❌ Failed to open camera: {camera_config.name}")
                return False
            
            # Configure camera settings
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_config.resolution[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_config.resolution[1])
            cap.set(cv2.CAP_PROP_FPS, camera_config.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
            
            # Store camera
            self.active_cameras[camera_config.camera_id] = cap
            self.camera_configs[camera_config.camera_id] = camera_config
            
            # Initialize tracking
            self.fps_counters[camera_config.camera_id] = []
            self.connection_stats[camera_config.camera_id] = {
                'connected_at': datetime.now(),
                'frames_captured': 0,
                'connection_drops': 0,
                'last_frame_time': None
            }
            
            # Start frame capture thread
            capture_thread = threading.Thread(
                target=self._capture_frames,
                args=(camera_config.camera_id,),
                daemon=True
            )
            capture_thread.start()
            self.connection_threads[camera_config.camera_id] = capture_thread
            
            camera_config.connection_status = 'connected'
            logger.info(f"✅ Camera connected successfully: {camera_config.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Camera connection failed: {camera_config.name} - {e}")
            camera_config.connection_status = 'failed'
            return False
    
    def _capture_frames(self, camera_id: str):
        """Professional frame capture with performance monitoring"""
        logger.info(f"📹 Starting frame capture: {camera_id}")
        
        cap = self.active_cameras[camera_id]
        config = self.camera_configs[camera_id]
        stats = self.connection_stats[camera_id]
        
        frame_times = []
        reconnect_attempts = 0
        max_reconnect_attempts = 3
        
        while camera_id in self.active_cameras and config.enabled:
            try:
                frame_start = time.time()
                
                ret, frame = cap.read()
                
                if ret and frame is not None:
                    # Store frame
                    self.frame_buffers[camera_id] = frame.copy()
                    self.last_frames[camera_id] = datetime.now()
                    
                    # Update statistics
                    stats['frames_captured'] += 1
                    stats['last_frame_time'] = datetime.now()
                    
                    # Calculate FPS
                    frame_time = time.time() - frame_start
                    frame_times.append(frame_time)
                    
                    if len(frame_times) > 30:  # Keep last 30 frame times
                        frame_times.pop(0)
                    
                    if len(frame_times) > 5:
                        avg_frame_time = sum(frame_times) / len(frame_times)
                        fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
                        self.fps_counters[camera_id] = [fps]  # Store current FPS
                    
                    reconnect_attempts = 0  # Reset on successful frame
                    
                else:
                    # Frame capture failed
                    logger.warning(f"⚠️ Frame capture failed: {camera_id}")
                    
                    if reconnect_attempts < max_reconnect_attempts:
                        logger.info(f"🔄 Attempting reconnection: {camera_id} ({reconnect_attempts + 1}/{max_reconnect_attempts})")
                        
                        # Try to reconnect
                        cap.release()
                        time.sleep(2)
                        
                        if config.source_type == 'ip_webcam':
                            video_url = config.connection_url.replace('/shot.jpg', '/video')
                            cap = cv2.VideoCapture(video_url)
                        else:
                            cap = cv2.VideoCapture(config.connection_url)
                        
                        if cap.isOpened():
                            self.active_cameras[camera_id] = cap
                            logger.info(f"✅ Reconnection successful: {camera_id}")
                        else:
                            reconnect_attempts += 1
                            stats['connection_drops'] += 1
                    else:
                        logger.error(f"❌ Max reconnection attempts reached: {camera_id}")
                        break
                
                # Frame rate control
                time.sleep(1.0 / config.fps if config.fps > 0 else 0.033)
                
            except Exception as e:
                logger.error(f"❌ Frame capture error: {camera_id} - {e}")
                time.sleep(1)
                reconnect_attempts += 1
                
                if reconnect_attempts >= max_reconnect_attempts:
                    break
        
        # Cleanup
        if cap:
            cap.release()
        
        if camera_id in self.active_cameras:
            del self.active_cameras[camera_id]
        
        config.connection_status = 'disconnected'
        logger.info(f"🔌 Frame capture stopped: {camera_id}")
    
    def disconnect_camera(self, camera_id: str) -> bool:
        """Professionally disconnect camera"""
        logger.info(f"🔌 Disconnecting camera: {camera_id}")
        
        try:
            # Mark as disabled
            if camera_id in self.camera_configs:
                self.camera_configs[camera_id].enabled = False
                self.camera_configs[camera_id].connection_status = 'disconnected'
            
            # Release video capture
            if camera_id in self.active_cameras:
                self.active_cameras[camera_id].release()
                del self.active_cameras[camera_id]
            
            # Clean up buffers
            if camera_id in self.frame_buffers:
                del self.frame_buffers[camera_id]
            
            if camera_id in self.last_frames:
                del self.last_frames[camera_id]
            
            if camera_id in self.fps_counters:
                del self.fps_counters[camera_id]
            
            if camera_id in self.connection_stats:
                del self.connection_stats[camera_id]
            
            logger.info(f"✅ Camera disconnected: {camera_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Camera disconnection failed: {camera_id} - {e}")
            return False
    
    def get_camera_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Get latest frame from camera"""
        return self.frame_buffers.get(camera_id)
    
    def get_camera_status(self, camera_id: str) -> Dict[str, Any]:
        """Get comprehensive camera status"""
        if camera_id not in self.camera_configs:
            return {'status': 'not_found'}
        
        config = self.camera_configs[camera_id]
        stats = self.connection_stats.get(camera_id, {})
        
        current_fps = 0
        if camera_id in self.fps_counters and self.fps_counters[camera_id]:
            current_fps = self.fps_counters[camera_id][-1]
        
        return {
            'camera_id': camera_id,
            'name': config.name,
            'source_type': config.source_type,
            'connection_status': config.connection_status,
            'enabled': config.enabled,
            'current_fps': round(current_fps, 1),
            'target_fps': config.fps,
            'resolution': f"{config.resolution[0]}x{config.resolution[1]}",
            'last_frame_time': self.last_frames.get(camera_id),
            'frames_captured': stats.get('frames_captured', 0),
            'connection_drops': stats.get('connection_drops', 0),
            'connected_since': stats.get('connected_at'),
            'last_test': config.last_connection_test
        }
    
    def get_all_camera_status(self) -> List[Dict[str, Any]]:
        """Get status of all cameras"""
        return [self.get_camera_status(camera_id) for camera_id in self.camera_configs.keys()]
    
    def create_ip_webcam_config(self, name: str, ip: str, port: int = 8080) -> CameraSource:
        """Create IP Webcam camera configuration"""
        camera_id = f"IPWEB_{ip.replace('.', '_')}_{port}"
        
        return CameraSource(
            camera_id=camera_id,
            name=name,
            source_type='ip_webcam',
            connection_url=f"http://{ip}:{port}/shot.jpg",
            resolution=(1280, 720),
            fps=25,
            timeout=10,
            retry_attempts=3
        )
    
    def create_local_camera_config(self, name: str, camera_index: int = 0) -> CameraSource:
        """Create local camera configuration"""
        camera_id = f"LOCAL_{camera_index}"
        
        return CameraSource(
            camera_id=camera_id,
            name=name,
            source_type='local',
            connection_url=str(camera_index),
            resolution=(1280, 720),
            fps=30,
            timeout=5,
            retry_attempts=2
        )
    
    def save_camera_configs(self, file_path: str = "configs/camera_configs.json"):
        """Save camera configurations to file"""
        try:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            
            configs_data = {}
            for camera_id, config in self.camera_configs.items():
                configs_data[camera_id] = {
                    'camera_id': config.camera_id,
                    'name': config.name,
                    'source_type': config.source_type,
                    'connection_url': config.connection_url,
                    'backup_url': config.backup_url,
                    'username': config.username,
                    'password': config.password,
                    'resolution': config.resolution,
                    'fps': config.fps,
                    'timeout': config.timeout,
                    'retry_attempts': config.retry_attempts,
                    'enabled': config.enabled
                }
            
            with open(file_path, 'w') as f:
                json.dump(configs_data, f, indent=2, default=str)
            
            logger.info(f"✅ Camera configurations saved: {file_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save camera configs: {e}")
    
    def load_camera_configs(self, file_path: str = "configs/camera_configs.json"):
        """Load camera configurations from file"""
        try:
            if not Path(file_path).exists():
                logger.info(f"📁 No camera config file found: {file_path}")
                return
            
            with open(file_path, 'r') as f:
                configs_data = json.load(f)
            
            for camera_id, config_dict in configs_data.items():
                config = CameraSource(**config_dict)
                self.camera_configs[camera_id] = config
            
            logger.info(f"✅ Camera configurations loaded: {len(configs_data)} cameras")
            
        except Exception as e:
            logger.error(f"❌ Failed to load camera configs: {e}")
    
    def discover_and_sync_cameras(self, company_id: str = "DEFAULT_COMPANY", network_range: str = "192.168.1.0/24") -> Dict[str, Any]:
        """
        Kameraları keşfet ve veritabanına senkronize et
        
        Args:
            company_id: Şirket ID'si
            network_range: Taranacak ağ aralığı
            
        Returns:
            Keşif ve senkronizasyon sonucu
        """
        try:
            from database_adapter import get_camera_discovery_manager
            from camera_discovery import IPCameraDiscovery
            
            result = {
                'network_scan': {},
                'ip_webcam_scan': {},
                'database_sync': {},
                'total_discovered': 0,
                'total_synced': 0,
                'success': False
            }
            
            logger.info(f"🔍 Starting comprehensive camera discovery for company: {company_id}")
            
            # 1. IP Camera Discovery (Professional cameras)
            logger.info("📹 Scanning for IP cameras...")
            ip_discovery = IPCameraDiscovery()
            network_result = ip_discovery.scan_network(network_range, timeout=2)
            result['network_scan'] = network_result
            
            # 2. IP Webcam Discovery (Phone cameras)  
            logger.info("📱 Scanning for IP Webcam apps...")
            ip_webcam_cameras = self.detect_ip_webcam_cameras(network_range)
            result['ip_webcam_scan'] = {
                'cameras': ip_webcam_cameras,
                'found_count': len(ip_webcam_cameras)
            }
            
            # 3. Combine all discovered cameras
            all_discovered = []
            
            # Add IP cameras
            if network_result.get('cameras'):
                all_discovered.extend(network_result['cameras'])
            
            # Add IP Webcam cameras (convert format)
            for webcam in ip_webcam_cameras:
                webcam_camera = {
                    'ip': webcam['ip'],
                    'port': webcam['port'],
                    'brand': 'IP Webcam',
                    'model': 'Mobile Camera',
                    'rtsp_url': f"http://{webcam['ip']}:{webcam['port']}/video",
                    'resolution': '1280x720',
                    'fps': 25
                }
                all_discovered.append(webcam_camera)
            
            result['total_discovered'] = len(all_discovered)
            logger.info(f"✅ Total cameras discovered: {result['total_discovered']}")
            
            # 4. Sync to database
            if all_discovered:
                logger.info("💾 Syncing discovered cameras to database...")
                discovery_manager = get_camera_discovery_manager()
                sync_result = discovery_manager.sync_discovered_cameras_to_db(company_id, all_discovered)
                result['database_sync'] = sync_result
                result['total_synced'] = sync_result['added'] + sync_result['updated']
                
                logger.info(f"✅ Database sync complete: {sync_result['added']} added, {sync_result['updated']} updated")
            else:
                logger.info("ℹ️ No cameras discovered, skipping database sync")
                result['database_sync'] = {'message': 'No cameras to sync'}
            
            result['success'] = True
            return result
            
        except Exception as e:
            logger.error(f"❌ Camera discovery and sync failed: {e}")
            result['success'] = False
            result['error'] = str(e)
            return result
    
    def sync_config_cameras_to_db(self, company_id: str, config_file_path: str = "configs/industrial_config.yaml") -> Dict[str, Any]:
        """
        Config dosyasındaki kameraları veritabanına senkronize et
        
        Args:
            company_id: Şirket ID'si
            config_file_path: Config dosyası yolu
            
        Returns:
            Senkronizasyon sonucu
        """
        try:
            import yaml
            from database_adapter import get_camera_discovery_manager
            
            result = {
                'config_loaded': False,
                'cameras_found': 0,
                'database_sync': {},
                'success': False
            }
            
            logger.info(f"🔧 Syncing config cameras to database for company: {company_id}")
            
            # Config dosyasını yükle
            if not Path(config_file_path).exists():
                logger.warning(f"⚠️ Config file not found: {config_file_path}")
                result['error'] = f"Config file not found: {config_file_path}"
                return result
            
            with open(config_file_path, 'r') as f:
                config = yaml.safe_load(f)
            
            cameras = config.get('cameras', {})
            result['config_loaded'] = True
            result['cameras_found'] = len(cameras)
            
            logger.info(f"📹 Found {len(cameras)} cameras in config file")
            
            # Veritabanına senkronize et
            if cameras:
                discovery_manager = get_camera_discovery_manager()
                sync_result = discovery_manager.sync_config_cameras_to_db(company_id, cameras)
                result['database_sync'] = sync_result
                
                logger.info(f"✅ Config sync complete: {sync_result['added']} added, {sync_result['updated']} updated")
            else:
                logger.info("ℹ️ No cameras in config file")
                result['database_sync'] = {'message': 'No cameras in config'}
            
            result['success'] = True
            return result
            
        except Exception as e:
            logger.error(f"❌ Config camera sync failed: {e}")
            result['success'] = False
            result['error'] = str(e)
            return result
    
    def get_database_cameras(self, company_id: str) -> List[Dict[str, Any]]:
        """
        Veritabanından şirket kameralarını getir
        
        Args:
            company_id: Şirket ID'si
            
        Returns:
            Kameralar listesi
        """
        try:
            from database_adapter import get_db_adapter
            
            db_adapter = get_db_adapter()
            
            query = '''
                SELECT camera_id, camera_name, location, ip_address, rtsp_url, 
                       resolution, fps, status, created_at, last_detection
                FROM cameras 
                WHERE company_id = ? AND status != 'deleted'
                ORDER BY created_at DESC
            '''
            
            results = db_adapter.execute_query(query, (company_id,), fetch_all=True)
            
            cameras = []
            for row in results:
                camera = {
                    'camera_id': row[0],
                    'name': row[1],
                    'location': row[2],
                    'ip_address': row[3],
                    'rtsp_url': row[4],
                    'resolution': row[5],
                    'fps': row[6],
                    'status': row[7],
                    'created_at': row[8],
                    'last_detection': row[9]
                }
                cameras.append(camera)
            
            logger.info(f"📹 Retrieved {len(cameras)} cameras from database for company: {company_id}")
            return cameras
            
        except Exception as e:
            logger.error(f"❌ Failed to get database cameras: {e}")
            return []
    
    def full_camera_sync(self, company_id: str = "DEFAULT_COMPANY", network_range: str = "192.168.1.0/24") -> Dict[str, Any]:
        """
        Kapsamlı kamera senkronizasyonu: Discovery + Config + Database
        
        Args:
            company_id: Şirket ID'si
            network_range: Taranacak ağ aralığı
            
        Returns:
            Tam senkronizasyon sonucu
        """
        try:
            result = {
                'discovery_result': {},
                'config_sync_result': {},
                'final_camera_count': 0,
                'success': False
            }
            
            logger.info(f"🚀 Starting full camera synchronization for company: {company_id}")
            
            # 1. Network discovery ve database sync
            discovery_result = self.discover_and_sync_cameras(company_id, network_range)
            result['discovery_result'] = discovery_result
            
            # 2. Config kameralarını sync et
            config_sync_result = self.sync_config_cameras_to_db(company_id)
            result['config_sync_result'] = config_sync_result
            
            # 3. Final kamera sayısını al
            final_cameras = self.get_database_cameras(company_id)
            result['final_camera_count'] = len(final_cameras)
            
            logger.info(f"✅ Full camera sync complete: {result['final_camera_count']} total cameras in database")
            
            result['success'] = True
            return result
            
        except Exception as e:
            logger.error(f"❌ Full camera sync failed: {e}")
            result['success'] = False
            result['error'] = str(e)
            return result

    def smart_test_camera_connection(self, ip_address: str, name: str = "Smart Detected Camera") -> Dict[str, Any]:
        """
        Akıllı kamera bağlantı testi - Sadece IP adresi ile
        
        Args:
            ip_address: Kamera IP adresi
            name: Kamera adı
            
        Returns:
            Test sonucu
        """
        logger.info(f"🧠 Smart camera test for {ip_address}")
        
        # Akıllı tespit sistemi
        detector = SmartCameraDetector()
        detection_result = detector.smart_detect_camera(ip_address)
        
        if not detection_result['success']:
            return {
                'success': False,
                'error': detection_result['error'],
                'detection_info': detection_result
            }
        
        # Tespit edilen bilgilerle kamera konfigürasyonu oluştur
        camera_config = RealCameraConfig(
            camera_id=f"SMART_{ip_address.replace('.', '_')}",
            name=name,
            ip_address=ip_address,
            port=detection_result['port'],
            protocol=detection_result['protocol'],
            stream_path=detection_result['path'],
            timeout=10
        )
        
        # Normal test yap
        test_result = self.test_real_camera_connection(camera_config)
        test_result['detection_info'] = detection_result
        
        return test_result

    def smart_discover_cameras(self, network_range: str = "192.168.1.0/24") -> List[Dict]:
        """
        Akıllı kamera keşfi - Gelişmiş tespit sistemi
        
        Args:
            network_range: Taranacak ağ aralığı
            
        Returns:
            Keşfedilen kameralar listesi
        """
        logger.info(f"🧠 Smart camera discovery for {network_range}")
        
        discovered_cameras = []
        detector = SmartCameraDetector()
        
        try:
            import ipaddress
            network = ipaddress.IPv4Network(network_range, strict=False)
            
            # Paralel tarama için ThreadPool
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def scan_ip(ip):
                try:
                    detection_result = detector.smart_detect_camera(str(ip))
                    if detection_result['success']:
                        return {
                            'ip': str(ip),
                            'model': detection_result['model'],
                            'protocol': detection_result['protocol'],
                            'port': detection_result['port'],
                            'path': detection_result['path'],
                            'stream_url': detection_result['url'],
                            'confidence': detection_result['confidence'],
                            'detection_info': detection_result
                        }
                except Exception as e:
                    logger.debug(f"Scan failed for {ip}: {e}")
                return None
            
            # Paralel tarama
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(scan_ip, ip): ip for ip in network.hosts()}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        discovered_cameras.append(result)
                        logger.info(f"📹 Smart discovered: {result['model']} at {result['ip']}")
            
            logger.info(f"✅ Smart discovery complete: {len(discovered_cameras)} cameras found")
            return discovered_cameras
            
        except Exception as e:
            logger.error(f"❌ Smart discovery failed: {e}")
            return []

# Global camera manager instance
camera_manager = ProfessionalCameraManager()

def get_camera_manager() -> ProfessionalCameraManager:
    """Get global camera manager instance"""
    return camera_manager

# Test function
def test_camera_manager():
    """Test the camera manager"""
    logger.info("🧪 Testing Professional Camera Manager")
    
    manager = get_camera_manager()
    
    # Test IP Webcam detection
    ip_cameras = manager.detect_ip_webcam_cameras("192.168.1.0/24")
    logger.info(f"📱 Found {len(ip_cameras)} IP Webcam cameras")
    
    # Test local camera
    local_camera = manager.create_local_camera_config("Laptop Camera", 0)
    test_result = manager.test_camera_connection(local_camera)
    logger.info(f"💻 Local camera test: {test_result['connection_status']}")
    
    # If IP cameras found, test first one
    if ip_cameras:
        ip_camera = ip_cameras[0]
        webcam_config = manager.create_ip_webcam_config(
            f"Phone Camera {ip_camera['ip']}", 
            ip_camera['ip'], 
            ip_camera['port']
        )
        test_result = manager.test_camera_connection(webcam_config)
        logger.info(f"📱 IP Webcam test: {test_result['connection_status']}")

if __name__ == "__main__":
    test_camera_manager() 