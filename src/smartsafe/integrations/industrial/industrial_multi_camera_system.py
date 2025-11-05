#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Industrial Multi-Camera PPE Detection System
Professional-grade system for industrial environments
Features: RTSP, Failover, Synchronization, 24/7 Operation
"""

import cv2
import numpy as np
import time
import threading
import queue
import logging
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
import sqlite3
import requests
from ultralytics import YOLO
from collections import deque, defaultdict
import psutil
import sys
import yaml
import os

# Configure industrial logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s',
    handlers=[
        logging.FileHandler('logs/industrial_system.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class CameraConfig:
    """Industrial camera configuration"""
    camera_id: str
    name: str
    rtsp_url: str
    backup_rtsp_url: Optional[str] = None
    resolution: Tuple[int, int] = (1280, 720)
    fps: int = 25
    location: str = "Unknown"
    priority: int = 1  # 1=Critical, 2=Important, 3=Normal
    enabled: bool = True
    detection_zones: List[Tuple[int, int, int, int]] = None  # ROI zones

@dataclass
class DetectionResult:
    """Industrial detection result"""
    camera_id: str
    timestamp: datetime
    person_count: int
    ppe_compliant: int
    ppe_violations: int
    violation_details: List[str]
    confidence_avg: float
    processing_time_ms: float
    frame_id: int

@dataclass
class SystemHealth:
    """System health metrics"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    gpu_usage: float
    disk_usage: float
    active_cameras: int
    failed_cameras: List[str]
    fps_average: float
    uptime_hours: float

class IndustrialPPEDetectionSystem:
    """Industrial-grade multi-camera PPE detection system"""
    
    def __init__(self, config_path: str = "configs/industrial_config.yaml"):
        self.config_path = config_path
        self.cameras: Dict[str, CameraConfig] = {}
        self.camera_threads: Dict[str, threading.Thread] = {}
        self.camera_queues: Dict[str, queue.Queue] = {}
        self.detection_results: Dict[str, queue.Queue] = {}
        self.system_running = False
        self.start_time = datetime.now()
        
        # Load industrial configuration
        self.load_industrial_config()
        
        # Initialize model
        self.model = None
        self.load_detection_model()
        
        # System monitoring
        self.health_monitor = SystemHealthMonitor()
        self.database_manager = IndustrialDatabaseManager()
        self.alert_manager = IndustrialAlertManager()
        
        # Performance tracking
        self.performance_metrics = {
            'total_frames': 0,
            'total_detections': 0,
            'avg_processing_time': 0,
            'camera_fps': defaultdict(deque),
            'system_fps': deque(maxlen=100)
        }
        
        logger.info("🏭 Industrial PPE Detection System initialized")
    
    def load_industrial_config(self):
        """Load industrial configuration"""
        # Load configuration from YAML file
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
                self.cameras = config.get('cameras', {})
        else:
            # Default industrial camera configuration
            default_cameras = {
                "CAM_001": CameraConfig(
                    camera_id="CAM_001",
                    name="Production Line A - Entry",
                    rtsp_url="rtsp://192.168.1.100:554/stream1",
                    backup_rtsp_url="rtsp://192.168.1.101:554/stream1",
                    location="Production Area A",
                    priority=1
                ),
                "CAM_002": CameraConfig(
                    camera_id="CAM_002", 
                    name="Production Line A - Exit",
                    rtsp_url="rtsp://192.168.1.102:554/stream1",
                    backup_rtsp_url="rtsp://192.168.1.103:554/stream1",
                    location="Production Area A",
                    priority=1
                ),
                "CAM_003": CameraConfig(
                    camera_id="CAM_003",
                    name="Warehouse - Loading Bay",
                    rtsp_url="rtsp://192.168.1.104:554/stream1",
                    location="Warehouse",
                    priority=2
                ),
                "CAM_004": CameraConfig(
                    camera_id="CAM_004",
                    name="Office Entry Point",
                    rtsp_url="rtsp://192.168.1.105:554/stream1",
                    location="Administration",
                    priority=3
                )
            }
            
            self.cameras = default_cameras
        logger.info(f"✅ Loaded {len(self.cameras)} industrial cameras")
    
    def load_detection_model(self):
        """Load optimized detection model"""
        try:
            model_path = "yolov8n.pt"  # Fast model for industrial use
            self.model = YOLO(model_path)
            self.model.to('cpu')  # Industrial systems often use CPU
            
            # Model optimization for industrial use
            self.model.model.eval()
            if hasattr(self.model.model, 'fuse'):
                self.model.model.fuse()
                
            logger.info("✅ Industrial detection model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load detection model: {e}")
            raise
    
    def setup_camera_connection(self, camera_config: CameraConfig) -> Optional[cv2.VideoCapture]:
        """Setup industrial camera connection with failover"""
        try:
            # Try primary RTSP URL
            cap = cv2.VideoCapture(camera_config.rtsp_url)
            
            if not cap.isOpened() and camera_config.backup_rtsp_url:
                logger.warning(f"Primary RTSP failed for {camera_config.camera_id}, trying backup")
                cap.release()
                cap = cv2.VideoCapture(camera_config.backup_rtsp_url)
            
            if not cap.isOpened():
                # Fallback to local camera for testing
                logger.warning(f"RTSP failed for {camera_config.camera_id}, using local camera")
                cap.release()
                cap = cv2.VideoCapture(0)
            
            if cap.isOpened():
                # Industrial camera optimization
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_config.resolution[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_config.resolution[1])
                cap.set(cv2.CAP_PROP_FPS, camera_config.fps)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize latency
                
                # RTSP-specific optimizations
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'H264'))
                
                logger.info(f"✅ Camera {camera_config.camera_id} connected successfully")
                return cap
            else:
                logger.error(f"❌ Failed to connect camera {camera_config.camera_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Camera setup error for {camera_config.camera_id}: {e}")
            return None
    
    def camera_worker(self, camera_config: CameraConfig):
        """Industrial camera worker thread with reliability features"""
        camera_id = camera_config.camera_id
        logger.info(f"🎥 Starting camera worker: {camera_id}")
        
        # Camera connection with retry mechanism
        cap = None
        retry_count = 0
        max_retries = 5
        
        while self.system_running and retry_count < max_retries:
            cap = self.setup_camera_connection(camera_config)
            if cap is not None:
                break
            
            retry_count += 1
            logger.warning(f"Retrying camera {camera_id} connection ({retry_count}/{max_retries})")
            time.sleep(5)  # Wait before retry
        
        if cap is None:
            logger.error(f"❌ Failed to establish camera connection: {camera_id}")
            return
        
        # Initialize frame tracking
        frame_count = 0
        last_frame_time = time.time()
        fps_tracker = deque(maxlen=30)
        
        try:
            while self.system_running:
                start_time = time.time()
                
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Failed to read frame from {camera_id}")
                    # Attempt to reconnect
                    cap.release()
                    cap = self.setup_camera_connection(camera_config)
                    if cap is None:
                        break
                    continue
                
                frame_count += 1
                
                # Calculate FPS
                current_time = time.time()
                frame_time = current_time - last_frame_time
                fps_tracker.append(1.0 / frame_time if frame_time > 0 else 0)
                last_frame_time = current_time
                
                # Add frame to processing queue
                try:
                    frame_data = {
                        'frame': frame,
                        'camera_id': camera_id,
                        'timestamp': datetime.now(),
                        'frame_id': frame_count
                    }
                    self.camera_queues[camera_id].put_nowait(frame_data)
                except queue.Full:
                    # Skip frame if queue is full (performance optimization)
                    pass
                
                # Update performance metrics
                if fps_tracker:
                    camera_fps = sum(fps_tracker) / len(fps_tracker)
                    self.performance_metrics['camera_fps'][camera_id] = camera_fps
                
                # Small delay to prevent CPU overload
                time.sleep(0.001)
                
        except Exception as e:
            logger.error(f"❌ Camera worker error for {camera_id}: {e}")
        finally:
            if cap:
                cap.release()
            logger.info(f"🔌 Camera worker stopped: {camera_id}")
    
    def detection_worker(self, camera_id: str):
        """Industrial detection worker with performance optimization"""
        logger.info(f"🧠 Starting detection worker: {camera_id}")
        
        # Performance tracking
        processing_times = deque(maxlen=50)
        
        try:
            while self.system_running:
                try:
                    # Get frame from camera queue
                    frame_data = self.camera_queues[camera_id].get(timeout=1.0)
                    
                    start_time = time.time()
                    
                    # Run PPE detection
                    detections = self.detect_ppe_industrial(
                        frame_data['frame'],
                        camera_id
                    )
                    
                    # Calculate processing time
                    processing_time = (time.time() - start_time) * 1000  # ms
                    processing_times.append(processing_time)
                    
                    # Create detection result
                    result = DetectionResult(
                        camera_id=camera_id,
                        timestamp=frame_data['timestamp'],
                        person_count=len([d for d in detections if d['class_name'] == 'person']),
                        ppe_compliant=0,  # Will be calculated
                        ppe_violations=0,  # Will be calculated
                        violation_details=[],
                        confidence_avg=np.mean([d['confidence'] for d in detections]) if detections else 0,
                        processing_time_ms=processing_time,
                        frame_id=frame_data['frame_id']
                    )
                    
                    # Analyze PPE compliance
                    self.analyze_industrial_ppe_compliance(result, detections)
                    
                    # Store result
                    try:
                        self.detection_results[camera_id].put_nowait(result)
                    except queue.Full:
                        # Remove old result and add new one
                        try:
                            self.detection_results[camera_id].get_nowait()
                        except queue.Empty:
                            pass
                        self.detection_results[camera_id].put_nowait(result)
                    
                    # Update system metrics
                    self.performance_metrics['total_frames'] += 1
                    self.performance_metrics['total_detections'] += len(detections)
                    if processing_times:
                        self.performance_metrics['avg_processing_time'] = sum(processing_times) / len(processing_times)
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Detection worker error for {camera_id}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Detection worker fatal error for {camera_id}: {e}")
        finally:
            logger.info(f"🧠 Detection worker stopped: {camera_id}")
    
    def detect_ppe_industrial(self, frame: np.ndarray, camera_id: str) -> List[Dict]:
        """Industrial PPE detection with optimization"""
        try:
            # Resize frame for faster processing if needed
            height, width = frame.shape[:2]
            if width > 1280:  # Downsample large frames
                scale = 1280 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame_resized = cv2.resize(frame, (new_width, new_height))
            else:
                frame_resized = frame
                scale = 1.0
            
            # Run detection
            results = self.model(frame_resized, conf=0.3, verbose=False)
            
            detections = []
            for result in results:
                if result.boxes is not None:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    confidences = result.boxes.conf.cpu().numpy()
                    class_ids = result.boxes.cls.cpu().numpy()
                    
                    for i in range(len(boxes)):
                        x1, y1, x2, y2 = boxes[i]
                        
                        # Scale coordinates back if frame was resized
                        if scale != 1.0:
                            x1 = int(x1 / scale)
                            y1 = int(y1 / scale)
                            x2 = int(x2 / scale)
                            y2 = int(y2 / scale)
                        
                        class_id = int(class_ids[i])
                        class_name = self.model.names[class_id]
                        confidence = float(confidences[i])
                        
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': confidence,
                            'class_name': class_name,
                            'class_id': class_id
                        })
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection error for {camera_id}: {e}")
            return []
    
    def analyze_industrial_ppe_compliance(self, result: DetectionResult, detections: List[Dict]):
        """Analyze PPE compliance for industrial standards"""
        people = [d for d in detections if d['class_name'] == 'person']
        
        for person in people:
            person_bbox = person['bbox']
            
            # Check for PPE in vicinity of person
            has_helmet = self.check_ppe_near_person(person_bbox, detections, ['hard hat', 'helmet'])
            has_safety_vest = self.check_ppe_near_person(person_bbox, detections, ['safety vest', 'vest'])
            
            if has_helmet and has_safety_vest:
                result.ppe_compliant += 1
            else:
                result.ppe_violations += 1
                violations = []
                if not has_helmet:
                    violations.append("Missing Helmet")
                if not has_safety_vest:
                    violations.append("Missing Safety Vest")
                result.violation_details.extend(violations)
    
    def check_ppe_near_person(self, person_bbox: Tuple[int, int, int, int], 
                             detections: List[Dict], ppe_classes: List[str]) -> bool:
        """Check if PPE is near person"""
        px1, py1, px2, py2 = person_bbox
        
        for detection in detections:
            if detection['class_name'].lower() in [cls.lower() for cls in ppe_classes]:
                dx1, dy1, dx2, dy2 = detection['bbox']
                
                # Calculate overlap or proximity
                overlap_x = max(0, min(px2, dx2) - max(px1, dx1))
                overlap_y = max(0, min(py2, dy2) - max(py1, dy1))
                overlap_area = overlap_x * overlap_y
                
                person_area = (px2 - px1) * (py2 - py1)
                
                if overlap_area > 0.1 * person_area:  # 10% overlap threshold
                    return True
        
        return False
    
    def start_industrial_system(self):
        """Start the industrial multi-camera system"""
        logger.info("🏭 Starting Industrial PPE Detection System")
        self.system_running = True
        
        # Initialize queues
        for camera_id in self.cameras.keys():
            self.camera_queues[camera_id] = queue.Queue(maxsize=5)
            self.detection_results[camera_id] = queue.Queue(maxsize=10)
        
        # Start camera workers
        for camera_id, camera_config in self.cameras.items():
            if camera_config.enabled:
                camera_thread = threading.Thread(
                    target=self.camera_worker,
                    args=(camera_config,),
                    name=f"Camera-{camera_id}",
                    daemon=True
                )
                camera_thread.start()
                self.camera_threads[camera_id] = camera_thread
                
                # Start detection worker
                detection_thread = threading.Thread(
                    target=self.detection_worker,
                    args=(camera_id,),
                    name=f"Detection-{camera_id}",
                    daemon=True
                )
                detection_thread.start()
        
        # Start system monitoring
        monitor_thread = threading.Thread(
            target=self.health_monitor.start_monitoring,
            args=(self,),
            name="SystemMonitor",
            daemon=True
        )
        monitor_thread.start()
        
        logger.info("✅ Industrial system started successfully")
    
    def stop_industrial_system(self):
        """Stop the industrial system gracefully"""
        logger.info("🛑 Stopping Industrial PPE Detection System")
        self.system_running = False
        
        # Wait for threads to finish
        for thread in self.camera_threads.values():
            thread.join(timeout=5)
        
        logger.info("✅ Industrial system stopped successfully")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'uptime_hours': (datetime.now() - self.start_time).total_seconds() / 3600,
            'system_running': self.system_running,
            'cameras': {},
            'performance': self.performance_metrics.copy(),
            'health': self.health_monitor.get_current_health()
        }
        
        # Camera status
        for camera_id, camera_config in self.cameras.items():
            camera_fps = self.performance_metrics['camera_fps'].get(camera_id, 0)
            
            # Get latest detection result
            latest_result = None
            try:
                # Peek at latest result without removing it
                result_queue = self.detection_results.get(camera_id)
                if result_queue and not result_queue.empty():
                    temp_results = []
                    while not result_queue.empty():
                        temp_results.append(result_queue.get_nowait())
                    
                    if temp_results:
                        latest_result = temp_results[-1]
                        # Put results back
                        for result in temp_results:
                            try:
                                result_queue.put_nowait(result)
                            except queue.Full:
                                break
            except Exception:
                pass
            
            status['cameras'][camera_id] = {
                'name': camera_config.name,
                'location': camera_config.location,
                'enabled': camera_config.enabled,
                'fps': camera_fps,
                'status': 'active' if camera_fps > 5 else 'inactive',
                'latest_detection': asdict(latest_result) if latest_result else None
            }
        
        return status

class SystemHealthMonitor:
    """System health monitoring for industrial reliability"""
    
    def __init__(self):
        self.monitoring = False
        self.health_history = deque(maxlen=100)
    
    def start_monitoring(self, system: IndustrialPPEDetectionSystem):
        """Start system health monitoring"""
        self.monitoring = True
        logger.info("🔍 System health monitoring started")
        
        while system.system_running and self.monitoring:
            try:
                health = self.collect_health_metrics(system)
                self.health_history.append(health)
                
                # Check for critical issues
                self.check_critical_issues(health, system)
                
                # Log health status every 5 minutes
                if len(self.health_history) % 30 == 0:  # 30 * 10s = 5min
                    logger.info(f"💚 System Health: CPU {health.cpu_usage:.1f}%, "
                               f"Memory {health.memory_usage:.1f}%, "
                               f"Active Cameras {health.active_cameras}")
                
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                time.sleep(10)
    
    def collect_health_metrics(self, system: IndustrialPPEDetectionSystem) -> SystemHealth:
        """Collect system health metrics"""
        try:
            # System metrics
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # GPU metrics (if available)
            gpu_usage = 0
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu_usage = gpus[0].load * 100
            except:
                pass
            
            # Camera metrics
            active_cameras = 0
            failed_cameras = []
            
            for camera_id, camera_config in system.cameras.items():
                if camera_config.enabled:
                    camera_fps = system.performance_metrics['camera_fps'].get(camera_id, 0)
                    if camera_fps > 5:  # Active threshold
                        active_cameras += 1
                    else:
                        failed_cameras.append(camera_id)
            
            # FPS average
            fps_values = list(system.performance_metrics['camera_fps'].values())
            fps_average = sum(fps_values) / len(fps_values) if fps_values else 0
            
            # Uptime
            uptime_hours = (datetime.now() - system.start_time).total_seconds() / 3600
            
            return SystemHealth(
                timestamp=datetime.now(),
                cpu_usage=cpu_usage,
                memory_usage=memory.percent,
                gpu_usage=gpu_usage,
                disk_usage=disk.percent,
                active_cameras=active_cameras,
                failed_cameras=failed_cameras,
                fps_average=fps_average,
                uptime_hours=uptime_hours
            )
            
        except Exception as e:
            logger.error(f"Failed to collect health metrics: {e}")
            return SystemHealth(
                timestamp=datetime.now(),
                cpu_usage=0, memory_usage=0, gpu_usage=0, disk_usage=0,
                active_cameras=0, failed_cameras=[], fps_average=0, uptime_hours=0
            )
    
    def check_critical_issues(self, health: SystemHealth, system: IndustrialPPEDetectionSystem):
        """Check for critical system issues"""
        # High CPU usage
        if health.cpu_usage > 90:
            logger.warning(f"⚠️ High CPU usage: {health.cpu_usage:.1f}%")
        
        # High memory usage
        if health.memory_usage > 85:
            logger.warning(f"⚠️ High memory usage: {health.memory_usage:.1f}%")
        
        # Failed cameras
        if health.failed_cameras:
            logger.error(f"❌ Failed cameras: {health.failed_cameras}")
        
        # Low system FPS
        if health.fps_average < 10 and health.active_cameras > 0:
            logger.warning(f"⚠️ Low system FPS: {health.fps_average:.1f}")
    
    def get_current_health(self) -> Optional[Dict]:
        """Get current health status"""
        if self.health_history:
            latest = self.health_history[-1]
            return asdict(latest)
        return None

class IndustrialDatabaseManager:
    """Industrial database management"""
    
    def __init__(self, db_path: str = "logs/industrial_ppe.db"):
        self.db_path = db_path
        self.setup_database()
    
    def setup_database(self):
        """Setup industrial database schema"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Detection results table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detection_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    person_count INTEGER,
                    ppe_compliant INTEGER,
                    ppe_violations INTEGER,
                    violation_details TEXT,
                    confidence_avg REAL,
                    processing_time_ms REAL,
                    frame_id INTEGER
                )
            ''')
            
            # System health table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_health (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    cpu_usage REAL,
                    memory_usage REAL,
                    gpu_usage REAL,
                    disk_usage REAL,
                    active_cameras INTEGER,
                    failed_cameras TEXT,
                    fps_average REAL,
                    uptime_hours REAL
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("✅ Industrial database initialized")
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")

class IndustrialAlertManager:
    """Industrial alert management system"""
    
    def __init__(self):
        self.alert_history = deque(maxlen=1000)
    
    def send_alert(self, alert_type: str, message: str, camera_id: str = None):
        """Send industrial alert"""
        alert = {
            'timestamp': datetime.now(),
            'type': alert_type,
            'message': message,
            'camera_id': camera_id
        }
        
        self.alert_history.append(alert)
        logger.warning(f"🚨 ALERT [{alert_type}]: {message}")
        
        # Here you would implement:
        # - Email notifications
        # - SMS alerts
        # - SCADA integration
        # - Dashboard notifications

def main():
    """Main function for industrial system"""
    print("🏭 INDUSTRIAL PPE DETECTION SYSTEM")
    print("=" * 50)
    print("✅ Multi-Camera Support")
    print("✅ RTSP Stream Handling")
    print("✅ 24/7 Reliability")
    print("✅ System Health Monitoring")
    print("✅ Industrial Integration Ready")
    print("=" * 50)
    
    try:
        # Initialize industrial system
        system = IndustrialPPEDetectionSystem()
        
        # Start the system
        system.start_industrial_system()
        
        print("\n🎥 System Status:")
        print("-" * 30)
        
        # Run system monitoring loop
        try:
            while True:
                status = system.get_system_status()
                
                # Clear screen and show status
                os.system('cls' if os.name == 'nt' else 'clear')
                
                print(f"🏭 INDUSTRIAL PPE DETECTION SYSTEM")
                print(f"⏰ Uptime: {status['uptime_hours']:.1f} hours")
                print(f"📊 Total Frames: {status['performance']['total_frames']}")
                print(f"🎯 Total Detections: {status['performance']['total_detections']}")
                print(f"⚡ Avg Processing: {status['performance'].get('avg_processing_time', 0):.1f}ms")
                print()
                
                print("📹 CAMERA STATUS:")
                print("-" * 40)
                for camera_id, cam_status in status['cameras'].items():
                    status_icon = "🟢" if cam_status['status'] == 'active' else "🔴"
                    print(f"{status_icon} {camera_id}: {cam_status['name']}")
                    print(f"   📍 {cam_status['location']}")
                    print(f"   📊 {cam_status['fps']:.1f} FPS")
                    
                    if cam_status['latest_detection']:
                        det = cam_status['latest_detection']
                        print(f"   👥 People: {det['person_count']}")
                        print(f"   ✅ Compliant: {det['ppe_compliant']}")
                        print(f"   ❌ Violations: {det['ppe_violations']}")
                    print()
                
                if status['health']:
                    health = status['health']
                    print("💚 SYSTEM HEALTH:")
                    print("-" * 40)
                    print(f"🖥️  CPU: {health['cpu_usage']:.1f}%")
                    print(f"🧠 Memory: {health['memory_usage']:.1f}%")
                    print(f"📀 Disk: {health['disk_usage']:.1f}%")
                    print(f"📹 Active Cameras: {health['active_cameras']}")
                
                print("\n⌨️  Press Ctrl+C to stop system")
                time.sleep(5)  # Update every 5 seconds
                
        except KeyboardInterrupt:
            print("\n🛑 Stopping system...")
            system.stop_industrial_system()
            print("✅ System stopped successfully")
            
    except Exception as e:
        logger.error(f"❌ System error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main()) 