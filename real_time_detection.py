"""
Real-time PPE Detection System
Modern computer vision with YOLOv8 and object tracking
"""

import cv2
import numpy as np
import yaml
import time
import threading
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict, deque
import sqlite3
from datetime import datetime

# Deep Learning
import torch
from ultralytics import YOLO

# Tracking
try:
    from deep_sort_realtime import DeepSort
    DEEPSORT_AVAILABLE = True
except ImportError:
    DEEPSORT_AVAILABLE = False
    print("⚠️  DeepSORT not available - using simple tracking")

# Audio alerts
import pygame
import playsound
from threading import Thread

# Custom utilities
from utils.data_utils import PPEDataLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Detection:
    """Detection data structure"""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    class_id: int
    class_name: str
    track_id: Optional[int] = None

@dataclass
class PersonStatus:
    """Person PPE status tracking for SH17 dataset"""
    track_id: int
    has_helmet: bool = False
    has_safety_vest: bool = False
    has_safety_suit: bool = False
    has_medical_suit: bool = False
    has_face_mask: bool = False
    has_face_guard: bool = False
    has_gloves: bool = False
    has_shoes: bool = False
    has_glasses: bool = False
    has_earmuffs: bool = False
    violation_start_time: Optional[float] = None
    last_seen: float = 0.0
    violation_count: int = 0
    alert_sent: bool = False

class PPEDetectionSystem:
    """Real-time PPE Detection System"""
    
    def __init__(self, config_path: str = "configs/config.yaml"):
        """Initialize the PPE detection system"""
        self.config = self.load_config(config_path)
        self.setup_system()
        self.setup_database()
        
        # Detection model
        self.model = self.load_model()
        
        # Object tracking
        if self.config['detection']['tracking_enabled'] and DEEPSORT_AVAILABLE:
            try:
                self.tracker = DeepSort(
                    max_age=self.config['tracking']['max_age'],
                    n_init=self.config['tracking']['min_hits'],
                    nms_max_overlap=self.config['tracking']['iou_threshold'],
                    max_cosine_distance=self.config['tracking']['deepsort']['max_cosine_distance'],
                    nn_budget=self.config['tracking']['deepsort']['nn_budget']
                )
                logger.info("DeepSORT tracking enabled")
            except Exception as e:
                logger.warning(f"DeepSORT initialization failed: {e}")
                self.tracker = None
        else:
            self.tracker = None
            if self.config['detection']['tracking_enabled']:
                logger.info("Using simple tracking (DeepSORT not available)")
        
        # Person status tracking
        self.person_status: Dict[int, PersonStatus] = {}
        self.violation_duration = self.config['detection']['violation_duration']
        
        # Alert system
        self.alert_cooldown = self.config['alerts']['violation_cooldown']
        self.last_alert_time = defaultdict(float)
        
        # Audio system
        if self.config['alerts']['audio_enabled']:
            self.setup_audio()
        
        # Performance monitoring
        self.fps_queue = deque(maxlen=30)
        
        logger.info("PPE Detection System initialized successfully")
    
    @staticmethod
    def load_config(config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            return {}
    
    def setup_system(self):
        """Setup system components"""
        # Create necessary directories
        Path(self.config['paths']['logs']).mkdir(parents=True, exist_ok=True)
        Path(self.config['paths']['assets']).mkdir(parents=True, exist_ok=True)
        
        # SH17 Dataset class names mapping (17 classes)
        self.class_names = {
            0: 'person',
            1: 'head',
            2: 'face',
            3: 'glasses',
            4: 'face_mask_medical',
            5: 'face_guard',
            6: 'ear',
            7: 'earmuffs',
            8: 'hands',
            9: 'gloves',
            10: 'foot',
            11: 'shoes',
            12: 'safety_vest',
            13: 'tools',
            14: 'helmet',
            15: 'medical_suit',
            16: 'safety_suit'
        }
        
        # Colors for visualization (SH17 Dataset)
        self.colors = {
            'person': (255, 255, 255),          # White
            'head': (255, 200, 200),            # Light Pink
            'face': (255, 180, 180),            # Pink
            'glasses': (0, 255, 255),           # Cyan
            'face_mask_medical': (255, 0, 255), # Magenta
            'face_guard': (255, 100, 255),     # Light Magenta
            'ear': (200, 200, 255),             # Light Blue
            'earmuffs': (150, 150, 255),        # Blue
            'hands': (255, 255, 200),           # Light Yellow
            'gloves': (255, 255, 0),            # Yellow
            'foot': (200, 255, 200),            # Light Green
            'shoes': (100, 255, 100),           # Green
            'safety_vest': (0, 255, 0),         # Green - Critical PPE
            'tools': (255, 165, 0),             # Orange
            'helmet': (0, 255, 0),              # Green - Critical PPE
            'medical_suit': (255, 255, 255),    # White
            'safety_suit': (0, 255, 255),       # Cyan
            'violation': (0, 0, 255),           # Red
            'compliant': (0, 255, 0)            # Green
        }
    
    def setup_database(self):
        """Setup SQLite database for logging"""
        try:
            db_path = self.config['database']['path']
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
            self.db_connection = sqlite3.connect(db_path, check_same_thread=False)
            
            # Create tables
            cursor = self.db_connection.cursor()
            
            # Detections table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS detections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    track_id INTEGER,
                    has_hard_hat BOOLEAN,
                    has_safety_vest BOOLEAN,
                    has_mask BOOLEAN,
                    violation_type TEXT,
                    confidence REAL,
                    bbox_x1 INTEGER,
                    bbox_y1 INTEGER,
                    bbox_x2 INTEGER,
                    bbox_y2 INTEGER
                )
            ''')
            
            # Violations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    track_id INTEGER,
                    violation_type TEXT,
                    duration REAL,
                    alert_sent BOOLEAN
                )
            ''')
            
            self.db_connection.commit()
            logger.info("Database setup completed")
            
        except Exception as e:
            logger.error(f"Database setup failed: {str(e)}")
            self.db_connection = None
    
    def setup_audio(self):
        """Setup audio alert system"""
        try:
            pygame.mixer.init()
            self.alert_sound_path = self.config['alerts']['audio']['alert_sound']
            
            # Create a simple alert sound if it doesn't exist
            if not Path(self.alert_sound_path).exists():
                logger.info("Creating default alert sound...")
                self.create_default_alert_sound()
            
            logger.info("Audio system setup completed")
            
        except Exception as e:
            logger.error(f"Audio setup failed: {str(e)}")
    
    def create_default_alert_sound(self):
        """Create a default alert sound using pygame"""
        try:
            import numpy as np
            
            # Generate a simple beep sound
            sample_rate = 22050
            duration = 0.5
            frequency = 880  # A5 note
            
            frames = int(duration * sample_rate)
            arr = np.zeros(frames)
            
            for i in range(frames):
                arr[i] = np.sin(2 * np.pi * frequency * i / sample_rate)
            
            # Save as WAV file
            import wave
            with wave.open(self.alert_sound_path, 'w') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes((arr * 32767).astype(np.int16).tobytes())
            
            logger.info(f"Default alert sound created: {self.alert_sound_path}")
            
        except Exception as e:
            logger.error(f"Failed to create default alert sound: {str(e)}")
    
    def load_model(self):
        """Load YOLO model"""
        try:
            model_path = self.config['model']['model_path']
            device = self.config['model']['device']
            
            # Force CPU if CUDA has issues
            if device == 'cuda' and not torch.cuda.is_available():
                device = 'cpu'
                logger.warning("CUDA not available, using CPU")
            
            # Load SH17 YOLOv9-e model
            model = YOLO(model_path)
            model.to(device)
            
            logger.info(f"Loaded SH17 YOLOv9-e model: {model_path}")
            logger.info(f"Model device: {device}")
            
            return model
            
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise

    def detect_objects(self, frame: np.ndarray) -> List[Detection]:
        """Detect objects in frame using SH17 model"""
        try:
            # Run inference
            results = self.model(frame, conf=0.3, verbose=False)
            
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        # Extract box data
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Get class name
                        class_name = self.class_names.get(class_id, f"class_{class_id}")
                        
                        # Create detection
                        detection = Detection(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            confidence=float(confidence),
                            class_id=class_id,
                            class_name=class_name
                        )
                        detections.append(detection)
            
            return detections
            
        except Exception as e:
            logger.error(f"Object detection failed: {str(e)}")
            return []

    def update_tracking(self, detections: List[Detection], frame: np.ndarray) -> List[Detection]:
        """Update object tracking"""
        if not self.tracker:
            return detections
        
        try:
            # Prepare detections for tracker
            det_list = []
            for det in detections:
                x1, y1, x2, y2 = det.bbox
                det_list.append([[x1, y1, x2, y2], det.confidence, det.class_name])
            
            # Update tracker
            tracks = self.tracker.update_tracks(det_list, frame=frame)
            
            # Update detections with track IDs
            tracked_detections = []
            for track in tracks:
                if track.is_confirmed():
                    x1, y1, x2, y2 = track.to_ltrb().astype(int)
                    
                    # Find matching detection
                    for det in detections:
                        det_x1, det_y1, det_x2, det_y2 = det.bbox
                        
                        # Calculate IoU
                        iou = self.calculate_iou(
                            (x1, y1, x2, y2),
                            (det_x1, det_y1, det_x2, det_y2)
                        )
                        
                        if iou > 0.5:  # Threshold for matching
                            det.track_id = track.track_id
                            tracked_detections.append(det)
                            break
            
            return tracked_detections
            
        except Exception as e:
            logger.error(f"Tracking update failed: {str(e)}")
            return detections
        
    def calculate_iou(self, box1: Tuple[int, int, int, int], 
                        box2: Tuple[int, int, int, int]) -> float:
        """Calculate Intersection over Union (IoU)"""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i <= x1_i or y2_i <= y1_i:
            return 0.0
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        
        # Calculate union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0

    def analyze_ppe_compliance(self, detections: List[Detection]) -> Dict[int, PersonStatus]:
        """Analyze PPE compliance for each person using SH17 dataset"""
        current_time = time.time()
        
        # Group detections by person
        person_detections = defaultdict(list)
        
        for det in detections:
            if det.class_name == 'person' and det.track_id is not None:
                person_detections[det.track_id].append(det)
        
        # Analyze each person's PPE status
        for track_id, person_dets in person_detections.items():
            if track_id not in self.person_status:
                self.person_status[track_id] = PersonStatus(track_id=track_id)
            
            status = self.person_status[track_id]
            status.last_seen = current_time
            
            # Check for PPE equipment near person
            person_bbox = person_dets[0].bbox
            
            # Reset PPE status
            status.has_helmet = False
            status.has_safety_vest = False
            status.has_safety_suit = False
            status.has_medical_suit = False
            status.has_face_mask = False
            status.has_face_guard = False
            status.has_gloves = False
            status.has_shoes = False
            status.has_glasses = False
            status.has_earmuffs = False
            
            # Check for PPE items (SH17 classes)
            for det in detections:
                if det.class_name in ['helmet', 'safety_vest', 'safety_suit', 'medical_suit', 
                                     'face_mask_medical', 'face_guard', 'gloves', 'shoes', 
                                     'glasses', 'earmuffs']:
                    if self.is_ppe_on_person(person_bbox, det.bbox):
                        if det.class_name == 'helmet':
                            status.has_helmet = True
                        elif det.class_name == 'safety_vest':
                            status.has_safety_vest = True
                        elif det.class_name == 'safety_suit':
                            status.has_safety_suit = True
                        elif det.class_name == 'medical_suit':
                            status.has_medical_suit = True
                        elif det.class_name == 'face_mask_medical':
                            status.has_face_mask = True
                        elif det.class_name == 'face_guard':
                            status.has_face_guard = True
                        elif det.class_name == 'gloves':
                            status.has_gloves = True
                        elif det.class_name == 'shoes':
                            status.has_shoes = True
                        elif det.class_name == 'glasses':
                            status.has_glasses = True
                        elif det.class_name == 'earmuffs':
                            status.has_earmuffs = True
            
            # Check for violations (Critical PPE: helmet, safety_vest, safety_suit)
            is_compliant = (status.has_helmet and 
                           (status.has_safety_vest or status.has_safety_suit))
            
            if not is_compliant:
                if status.violation_start_time is None:
                    status.violation_start_time = current_time
                else:
                    violation_duration = current_time - status.violation_start_time
                    if violation_duration >= self.violation_duration and not status.alert_sent:
                        self.trigger_alert(status, violation_duration)
                        status.alert_sent = True
                        status.violation_count += 1
            else:
                status.violation_start_time = None
                status.alert_sent = False
        
        # Clean up old tracks
        self.cleanup_old_tracks(current_time)
        
        return self.person_status
        
    def is_ppe_on_person(self, person_bbox: Tuple[int, int, int, int], 
                        ppe_bbox: Tuple[int, int, int, int]) -> bool:
        """Check if PPE item is associated with person"""
        # Calculate overlap or proximity
        iou = self.calculate_iou(person_bbox, ppe_bbox)
        return iou > 0.1  # Threshold for association

    def cleanup_old_tracks(self, current_time: float, max_age: float = 5.0):
        """Remove old tracks that haven't been seen recently"""
        to_remove = []
        for track_id, status in self.person_status.items():
            if current_time - status.last_seen > max_age:
                to_remove.append(track_id)
        
        for track_id in to_remove:
            del self.person_status[track_id]

    def trigger_alert(self, status: PersonStatus, violation_duration: float):
        """Trigger alert for PPE violation"""
        try:
            current_time = time.time()
            
            # Check cooldown
            if current_time - self.last_alert_time[status.track_id] < self.alert_cooldown:
                return
            
            self.last_alert_time[status.track_id] = current_time
            
            # Determine violation type (SH17 dataset)
            violations = []
            if not status.has_helmet:
                violations.append("No Helmet")
            if not status.has_safety_vest and not status.has_safety_suit:
                violations.append("No Safety Vest/Suit")
            
            violation_type = ", ".join(violations)
            
            logger.warning(f"PPE VIOLATION - Track ID: {status.track_id}, "
                            f"Violations: {violation_type}, Duration: {violation_duration:.1f}s")
            
            # Audio alert
            if self.config['alerts']['audio_enabled']:
                Thread(target=self.play_alert_sound, daemon=True).start()
            
            # Database logging
            if self.db_connection:
                self.log_violation(status, violation_type, violation_duration)
            
        except Exception as e:
            logger.error(f"Alert trigger failed: {str(e)}")

    def play_alert_sound(self):
        """Play alert sound"""
        try:
            if Path(self.alert_sound_path).exists():
                pygame.mixer.music.load(self.alert_sound_path)
                pygame.mixer.music.play()
        except Exception as e:
            logger.error(f"Failed to play alert sound: {str(e)}")

    def log_violation(self, status: PersonStatus, violation_type: str, duration: float):
        """Log violation to database"""
        try:
            cursor = self.db_connection.cursor()
            cursor.execute('''
                INSERT INTO violations (track_id, violation_type, duration, alert_sent)
                VALUES (?, ?, ?, ?)
            ''', (status.track_id, violation_type, duration, True))
            self.db_connection.commit()
        except Exception as e:
            logger.error(f"Database logging failed: {str(e)}")

    def draw_detections(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """Draw detections and status on frame"""
        try:
            # Draw detections
            for det in detections:
                x1, y1, x2, y2 = det.bbox
                color = self.colors.get(det.class_name, (255, 255, 255))
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label
                label = f"{det.class_name} {det.confidence:.2f}"
                if det.track_id is not None:
                    label += f" ID:{det.track_id}"
                
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                                (x1 + label_size[0], y1), color, -1)
                cv2.putText(frame, label, (x1, y1 - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            
            # Draw person status (SH17 dataset)
            y_offset = 30
            for track_id, status in self.person_status.items():
                # Status text
                ppe_status = []
                if status.has_helmet:
                    ppe_status.append("✓ Helmet")
                else:
                    ppe_status.append("✗ Helmet")
                
                if status.has_safety_vest or status.has_safety_suit:
                    ppe_status.append("✓ Safety Vest/Suit")
                else:
                    ppe_status.append("✗ Safety Vest/Suit")
                
                if status.has_face_mask or status.has_face_guard:
                    ppe_status.append("✓ Face Protection")
                else:
                    ppe_status.append("✗ Face Protection")
                
                status_text = f"Person {track_id}: {' | '.join(ppe_status)}"
                
                # Color based on compliance (SH17 dataset)
                is_compliant = (status.has_helmet and 
                              (status.has_safety_vest or status.has_safety_suit))
                text_color = self.colors['compliant'] if is_compliant else self.colors['violation']
                
                cv2.putText(frame, status_text, (10, y_offset), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
                y_offset += 25
                
                # Violation timer
                if status.violation_start_time is not None:
                    violation_duration = time.time() - status.violation_start_time
                    timer_text = f"  Violation Timer: {violation_duration:.1f}s"
                    cv2.putText(frame, timer_text, (10, y_offset), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.colors['violation'], 2)
                    y_offset += 20
            
            # Draw FPS
            if self.fps_queue:
                current_fps = 1.0 / (sum(self.fps_queue) / len(self.fps_queue))
                fps_text = f"FPS: {current_fps:.1f}"
                cv2.putText(frame, fps_text, (frame.shape[1] - 150, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            return frame
            
        except Exception as e:
            logger.error(f"Drawing failed: {str(e)}")
            return frame

    def run_detection(self, source: Optional[str] = None):
        """Run real-time detection"""
        try:
            # Setup video source
            if source is None:
                source = self.config['video']['source']
            
            # Convert source to appropriate type
            if isinstance(source, str) and source.isdigit():
                source = int(source)  # Convert string numbers to int for webcam
            
            logger.info(f"Using video source: {source} (type: {type(source)})")
            cap = cv2.VideoCapture(source)
            
            # Set video properties
            if isinstance(source, int):  # Webcam
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config['video']['resolution'][0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config['video']['resolution'][1])
                cap.set(cv2.CAP_PROP_FPS, self.config['video']['fps'])
            
            logger.info(f"Starting detection on source: {source}")
            logger.info("Press 'q' to quit, 's' to save screenshot")
            
            frame_count = 0
            
            while True:
                start_time = time.time()
                
                ret, frame = cap.read()
                if not ret:
                    logger.error("Failed to read frame")
                    break
                
                # Detect objects
                detections = self.detect_objects(frame)
                
                # Update tracking
                detections = self.update_tracking(detections, frame)
                
                # Analyze PPE compliance
                person_status = self.analyze_ppe_compliance(detections)
                
                # Draw results
                frame = self.draw_detections(frame, detections)
                
                # Calculate FPS
                frame_time = time.time() - start_time
                self.fps_queue.append(frame_time)
                
                # Display frame
                cv2.imshow('PPE Detection System', frame)
                
                # Handle keyboard input
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    # Save screenshot
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = f"screenshot_{timestamp}.jpg"
                    cv2.imwrite(screenshot_path, frame)
                    logger.info(f"Screenshot saved: {screenshot_path}")
                
                frame_count += 1
                
                # Log stats every 100 frames
                if frame_count % 100 == 0:
                    avg_fps = 1.0 / (sum(self.fps_queue) / len(self.fps_queue))
                    logger.info(f"Processed {frame_count} frames, Avg FPS: {avg_fps:.1f}")
            
            cap.release()
            cv2.destroyAllWindows()
            
            if self.db_connection:
                self.db_connection.close()
            
            logger.info("Detection completed")
            
        except Exception as e:
            logger.error(f"Detection failed: {str(e)}")
            raise

# Main execution
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='PPE Detection System')
    parser.add_argument('--source', type=str, default=None, 
                       help='Video source (webcam index, IP camera URL, or video file path)')
    parser.add_argument('--config', type=str, default="configs/config.yaml",
                       help='Configuration file path')
    
    args = parser.parse_args()
    
    try:
        # Initialize detection system
        ppe_detector = PPEDetectionSystem(config_path=args.config)
        
        # Run detection with specified source
        ppe_detector.run_detection(source=args.source)
        
    except KeyboardInterrupt:
        logger.info("Detection stopped by user")
    except Exception as e:
        logger.error(f"System failed: {str(e)}")
        exit(1) 