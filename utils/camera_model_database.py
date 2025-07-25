#!/usr/bin/env python3
"""
SmartSafe AI - Kamera Modeli Veritabanı
Genişletilmiş kamera modeli desteği ve otomatik tespit
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

@dataclass
class CameraModelInfo:
    """Kamera modeli bilgileri"""
    name: str
    manufacturer: str
    ports: List[int]
    paths: List[str]
    headers: List[str]
    default_rtsp: str
    default_http: str
    default_credentials: Dict[str, str]
    features: List[str]
    resolution_support: List[str]
    fps_support: List[int]
    codec_support: List[str]

class CameraModelDatabase:
    """Genişletilmiş kamera modeli veritabanı"""
    
    def __init__(self, db_file: str = "data/models/camera_models.json"):
        self.db_file = db_file
        self.models = self._load_database()
    
    def _load_database(self) -> Dict[str, CameraModelInfo]:
        """Veritabanını yükle"""
        default_models = {
            'hikvision': CameraModelInfo(
                name='Hikvision IP Camera',
                manufacturer='Hikvision',
                ports=[554, 80, 8000, 8080, 443, 9000],
                paths=[
                    '/Streaming/Channels/101',
                    '/ISAPI/Streaming/channels/101',
                    '/doc/page/login.asp',
                    '/ISAPI/System/deviceInfo',
                    '/ISAPI/System/deviceCapabilities'
                ],
                headers=['Server: App-webs/', 'Server: uc-httpd', 'Server: Hikvision'],
                default_rtsp='rtsp://{ip}:554/Streaming/Channels/101',
                default_http='http://{ip}:80/ISAPI/Streaming/channels/101',
                default_credentials={'username': 'admin', 'password': 'admin'},
                features=['ptz', 'night_vision', 'motion_detection', 'audio'],
                resolution_support=['1920x1080', '1280x720', '640x480'],
                fps_support=[25, 30, 15, 10],
                codec_support=['H.264', 'H.265', 'MJPEG']
            ),
            'dahua': CameraModelInfo(
                name='Dahua IP Camera',
                manufacturer='Dahua',
                ports=[554, 80, 37777, 443, 9000, 37778],
                paths=[
                    '/cam/realmonitor',
                    '/cgi-bin/magicBox.cgi',
                    '/cgi-bin/configManager.cgi',
                    '/cgi-bin/global.cgi',
                    '/cgi-bin/deviceInfo.cgi'
                ],
                headers=['Server: DNVRS-Webs', 'Server: Dahua', 'Server: DNVRS'],
                default_rtsp='rtsp://{ip}:554/cam/realmonitor',
                default_http='http://{ip}:80/cgi-bin/magicBox.cgi',
                default_credentials={'username': 'admin', 'password': 'admin'},
                features=['ptz', 'night_vision', 'motion_detection', 'audio', 'smart_detection'],
                resolution_support=['2688x1520', '1920x1080', '1280x720', '640x480'],
                fps_support=[30, 25, 15, 10],
                codec_support=['H.264', 'H.265', 'MJPEG', 'H.264+']
            ),
            'axis': CameraModelInfo(
                name='Axis IP Camera',
                manufacturer='Axis',
                ports=[554, 80, 443, 3000, 3001],
                paths=[
                    '/axis-cgi/jpg/image.cgi',
                    '/view/viewer_index.shtml',
                    '/onvif/device_service',
                    '/axis-cgi/param.cgi',
                    '/axis-cgi/admin/restart.cgi'
                ],
                headers=['Server: AXIS', 'Server: Axis', 'Server: AXIS-Web-Server'],
                default_rtsp='rtsp://{ip}:554/axis-media/media.amp',
                default_http='http://{ip}:80/axis-cgi/jpg/image.cgi',
                default_credentials={'username': 'root', 'password': 'pass'},
                features=['ptz', 'night_vision', 'motion_detection', 'audio', 'analytics'],
                resolution_support=['1920x1080', '1280x720', '800x600', '640x480'],
                fps_support=[30, 25, 15, 10],
                codec_support=['H.264', 'H.265', 'MJPEG']
            ),
            'foscam': CameraModelInfo(
                name='Foscam IP Camera',
                manufacturer='Foscam',
                ports=[88, 554, 80, 443, 8080],
                paths=[
                    '/videostream.cgi',
                    '/snapshot.cgi',
                    '/cgi-bin/CGIProxy.fcgi',
                    '/cgi-bin/global.cgi',
                    '/cgi-bin/deviceInfo.cgi'
                ],
                headers=['Server: Foscam', 'Server: uc-httpd', 'Server: Foscam-Webs'],
                default_rtsp='rtsp://{ip}:554/videoMain',
                default_http='http://{ip}:88/videostream.cgi',
                default_credentials={'username': 'admin', 'password': 'admin'},
                features=['ptz', 'night_vision', 'motion_detection', 'audio', 'two_way_audio'],
                resolution_support=['1920x1080', '1280x720', '640x480'],
                fps_support=[30, 25, 15, 10],
                codec_support=['H.264', 'MJPEG']
            ),
            'generic': CameraModelInfo(
                name='Generic IP Camera',
                manufacturer='Generic',
                ports=[8080, 80, 554, 443, 8000, 9000],
                paths=[
                    '/video',
                    '/shot.jpg',
                    '/image.jpg',
                    '/snapshot',
                    '/live',
                    '/stream'
                ],
                headers=[],
                default_rtsp='rtsp://{ip}:554/stream',
                default_http='http://{ip}:8080/video',
                default_credentials={'username': '', 'password': ''},
                features=['basic_streaming'],
                resolution_support=['1280x720', '640x480'],
                fps_support=[25, 30, 15],
                codec_support=['MJPEG', 'H.264']
            ),
            'uniview': CameraModelInfo(
                name='Uniview IP Camera',
                manufacturer='Uniview',
                ports=[554, 80, 8080, 443, 37777],
                paths=[
                    '/cgi-bin/realmonitor.cgi',
                    '/cgi-bin/deviceInfo.cgi',
                    '/cgi-bin/global.cgi',
                    '/cgi-bin/magicBox.cgi'
                ],
                headers=['Server: Uniview', 'Server: Uniview-Webs'],
                default_rtsp='rtsp://{ip}:554/realmonitor.cgi',
                default_http='http://{ip}:80/cgi-bin/realmonitor.cgi',
                default_credentials={'username': 'admin', 'password': 'admin'},
                features=['ptz', 'night_vision', 'motion_detection', 'audio'],
                resolution_support=['1920x1080', '1280x720', '640x480'],
                fps_support=[25, 30, 15],
                codec_support=['H.264', 'H.265', 'MJPEG']
            ),
            'hikvision_dvr': CameraModelInfo(
                name='Hikvision DVR/NVR',
                manufacturer='Hikvision',
                ports=[554, 80, 8000, 8080, 443, 9000],
                paths=[
                    '/ISAPI/Streaming/channels/101',
                    '/ISAPI/System/deviceInfo',
                    '/doc/page/login.asp',
                    '/ISAPI/System/deviceCapabilities'
                ],
                headers=['Server: App-webs/', 'Server: uc-httpd'],
                default_rtsp='rtsp://{ip}:554/Streaming/Channels/101',
                default_http='http://{ip}:80/ISAPI/Streaming/channels/101',
                default_credentials={'username': 'admin', 'password': 'admin'},
                features=['recording', 'playback', 'ptz', 'motion_detection'],
                resolution_support=['1920x1080', '1280x720', '640x480'],
                fps_support=[25, 30, 15],
                codec_support=['H.264', 'H.265', 'MJPEG']
            ),
            'dahua_nvr': CameraModelInfo(
                name='Dahua NVR',
                manufacturer='Dahua',
                ports=[554, 80, 37777, 443, 9000],
                paths=[
                    '/cgi-bin/magicBox.cgi',
                    '/cgi-bin/configManager.cgi',
                    '/cgi-bin/global.cgi',
                    '/cgi-bin/deviceInfo.cgi'
                ],
                headers=['Server: DNVRS-Webs', 'Server: Dahua'],
                default_rtsp='rtsp://{ip}:554/cam/realmonitor',
                default_http='http://{ip}:80/cgi-bin/magicBox.cgi',
                default_credentials={'username': 'admin', 'password': 'admin'},
                features=['recording', 'playback', 'ptz', 'motion_detection'],
                resolution_support=['2688x1520', '1920x1080', '1280x720'],
                fps_support=[30, 25, 15],
                codec_support=['H.264', 'H.265', 'H.264+']
            ),
            'android_ip_webcam': CameraModelInfo(
                name='Android IP Webcam',
                manufacturer='Android',
                ports=[8080, 80, 443],
                paths=[
                    '/shot.jpg',
                    '/video',
                    '/audio',
                    '/settings',
                    '/status'
                ],
                headers=['Server: IP Webcam', 'Server: Android'],
                default_rtsp='rtsp://{ip}:8080/video',
                default_http='http://{ip}:8080/shot.jpg',
                default_credentials={'username': '', 'password': ''},
                features=['mobile_camera', 'audio', 'motion_detection'],
                resolution_support=['1280x720', '640x480', '320x240'],
                fps_support=[30, 25, 15, 10],
                codec_support=['MJPEG', 'H.264']
            ),
            'raspberry_pi_camera': CameraModelInfo(
                name='Raspberry Pi Camera',
                manufacturer='Raspberry Pi',
                ports=[8080, 80, 443, 8000],
                paths=[
                    '/stream.mjpg',
                    '/image.jpg',
                    '/video',
                    '/snapshot'
                ],
                headers=['Server: Raspberry Pi', 'Server: Motion'],
                default_rtsp='rtsp://{ip}:8080/stream.mjpg',
                default_http='http://{ip}:8080/stream.mjpg',
                default_credentials={'username': '', 'password': ''},
                features=['motion_detection', 'recording'],
                resolution_support=['1280x720', '640x480'],
                fps_support=[30, 25, 15],
                codec_support=['MJPEG', 'H.264']
            )
        }
        
        # Dosyadan yükle veya varsayılan kullan
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    models = {}
                    for model_id, model_data in data.items():
                        models[model_id] = CameraModelInfo(**model_data)
                    return models
            except Exception as e:
                logger.warning(f"Database file load error: {e}, using defaults")
        
        return default_models
    
    def save_database(self):
        """Veritabanını kaydet"""
        try:
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            data = {}
            for model_id, model_info in self.models.items():
                data[model_id] = {
                    'name': model_info.name,
                    'manufacturer': model_info.manufacturer,
                    'ports': model_info.ports,
                    'paths': model_info.paths,
                    'headers': model_info.headers,
                    'default_rtsp': model_info.default_rtsp,
                    'default_http': model_info.default_http,
                    'default_credentials': model_info.default_credentials,
                    'features': model_info.features,
                    'resolution_support': model_info.resolution_support,
                    'fps_support': model_info.fps_support,
                    'codec_support': model_info.codec_support
                }
            
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Database saved to {self.db_file}")
            
        except Exception as e:
            logger.error(f"Database save error: {e}")
    
    def get_all_models(self) -> List[str]:
        """Tüm model ID'lerini getir"""
        return list(self.models.keys())
    
    def get_model_info(self, model_id: str) -> Optional[CameraModelInfo]:
        """Model bilgilerini getir"""
        return self.models.get(model_id)
    
    def get_models_by_manufacturer(self, manufacturer: str) -> List[str]:
        """Üreticiye göre modelleri getir"""
        return [
            model_id for model_id, model_info in self.models.items()
            if model_info.manufacturer.lower() == manufacturer.lower()
        ]
    
    def get_models_by_feature(self, feature: str) -> List[str]:
        """Özelliğe göre modelleri getir"""
        return [
            model_id for model_id, model_info in self.models.items()
            if feature.lower() in [f.lower() for f in model_info.features]
        ]
    
    def add_custom_model(self, model_id: str, model_info: CameraModelInfo):
        """Özel model ekle"""
        self.models[model_id] = model_info
        self.save_database()
        logger.info(f"Custom model added: {model_id}")
    
    def remove_model(self, model_id: str):
        """Model kaldır"""
        if model_id in self.models:
            del self.models[model_id]
            self.save_database()
            logger.info(f"Model removed: {model_id}")
    
    def detect_camera_model(self, ip_address: str, port: int = 80) -> Optional[Dict[str, Any]]:
        """IP adresinden kamera modelini tespit et"""
        import requests
        
        for model_id, model_info in self.models.items():
            try:
                # HTTP başlıklarını kontrol et
                response = requests.get(f"http://{ip_address}:{port}", 
                                     timeout=5, 
                                     allow_redirects=False)
                
                if response.status_code == 200:
                    server_header = response.headers.get('Server', '').lower()
                    
                    # Server header kontrolü
                    for header in model_info.headers:
                        if header.lower() in server_header:
                            return {
                                'model_id': model_id,
                                'confidence': 0.9,
                                'detected_port': port,
                                'server_header': server_header
                            }
                    
                    # HTML içeriğinde model belirtisi ara
                    content = response.text.lower()
                    if (model_info.manufacturer.lower() in content or 
                        model_info.name.lower() in content):
                        return {
                            'model_id': model_id,
                            'confidence': 0.7,
                            'detected_port': port,
                            'content_match': True
                        }
                        
            except Exception as e:
                logger.debug(f"Model detection error for {model_id}: {e}")
                continue
        
        return None

def get_camera_database() -> CameraModelDatabase:
    """Kamera veritabanı instance'ı getir"""
    return CameraModelDatabase()

# Global instance
_camera_db = None

def get_camera_db() -> CameraModelDatabase:
    """Global kamera veritabanı instance'ı"""
    global _camera_db
    if _camera_db is None:
        _camera_db = CameraModelDatabase()
    return _camera_db 