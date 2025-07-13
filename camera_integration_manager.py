#!/usr/bin/env python3
"""
SmartSafe AI - Professional Camera Integration Manager
Enterprise-grade camera management with IP Webcam, RTSP, and local camera support
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class CameraSource:
    """Professional camera source configuration"""
    camera_id: str
    name: str
    source_type: str  # 'ip_webcam', 'rtsp', 'local', 'usb'
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
            
            logger.info(f"✅ Camera test complete: {camera_config.name} - {test_result['connection_status']}")
            
        except Exception as e:
            test_result['error_message'] = str(e)
            test_result['connection_status'] = 'failed'
            logger.error(f"❌ Camera test failed: {camera_config.name} - {e}")
        
        return test_result
    
    def _test_ip_webcam(self, config: CameraSource) -> Dict:
        """Test IP Webcam specific connection"""
        result = {}
        
        try:
            # Test basic HTTP connection
            response = requests.get(config.connection_url, timeout=config.timeout)
            if response.status_code == 200:
                result['features']['mjpeg_support'] = True
                
                # Test video stream
                video_url = config.connection_url.replace('/shot.jpg', '/video')
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
            result['error_message'] = str(e)
        
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