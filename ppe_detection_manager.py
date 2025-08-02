"""
SmartSafe AI - PPE Detection Manager
Professional PPE Detection System with Multi-Class Support
"""

import cv2
import numpy as np
import torch
from ultralytics import YOLO
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PPEDetectionManager:
    """
    Professional PPE Detection Manager
    Supports multi-class detection for different sectors
    """
    
    def __init__(self):
        self.ppe_model = None
        self.person_model = None
        self.sector_ppe_mapping = self._initialize_sector_ppe_mapping()
        self.detection_history = {}
        self.performance_metrics = {}
        
    def _initialize_sector_ppe_mapping(self) -> Dict[str, List[str]]:
        """Initialize sector-specific PPE requirements"""
        return {
            'construction': ['helmet', 'safety_vest', 'safety_shoes'],
            'manufacturing': ['helmet', 'safety_vest', 'gloves'],
            'chemical': ['helmet', 'respirator', 'gloves', 'safety_glasses'],
            'food': ['hair_net', 'gloves', 'apron'],
            'warehouse': ['helmet', 'safety_vest', 'safety_shoes'],
            'energy': ['helmet', 'safety_vest', 'safety_shoes', 'gloves'],
            'petrochemical': ['helmet', 'respirator', 'safety_vest', 'gloves'],
            'marine': ['helmet', 'life_vest', 'safety_shoes'],
            'aviation': ['aviation_helmet', 'reflective_vest', 'ear_protection'],
            'general': ['helmet', 'safety_vest']
        }
    
    def load_models(self, device: str = 'auto') -> bool:
        """Load PPE and person detection models"""
        try:
            logger.info("🔄 Loading PPE detection models...")
            
            # Production CUDA handler
            try:
                from production_cuda_handler import get_production_cuda_handler
                cuda_handler = get_production_cuda_handler()
                device = cuda_handler.get_safe_device()
                logger.info(f"✅ Production CUDA handler: {device}")
            except ImportError:
                # Fallback to local CUDA test
                if device == 'auto':
                    if torch.cuda.is_available():
                        try:
                            # Test CUDA functionality
                            test_tensor = torch.zeros(1, 3, 640, 640).cuda()
                            device = 'cuda'
                            logger.info("✅ CUDA test passed, using GPU")
                        except Exception as cuda_error:
                            logger.warning(f"⚠️ CUDA test failed: {cuda_error}, falling back to CPU")
                            device = 'cpu'
                    else:
                        device = 'cpu'
            
            # Load YOLOv8 models
            self.person_model = YOLO('yolov8n.pt')  # Person detection
            self.ppe_model = YOLO('yolov8n.pt')     # PPE detection (will be enhanced)
            
            # Move to device with error handling
            try:
                self.person_model.to(device)
                self.ppe_model.to(device)
                logger.info(f"✅ Models loaded successfully on {device}")
            except Exception as device_error:
                logger.warning(f"⚠️ Device assignment failed: {device_error}, using CPU")
                device = 'cpu'
                self.person_model.to('cpu')
                self.ppe_model.to('cpu')
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error loading models: {e}")
            return False
    
    def detect_ppe_comprehensive(self, frame: np.ndarray, sector: str = 'general') -> Dict[str, Any]:
        """
        Comprehensive PPE detection with sector-specific validation
        """
        try:
            if frame is None:
                return self._create_error_response("Invalid frame")
            
            # Step 1: Person Detection
            person_detections = self._detect_persons(frame)
            if not person_detections:
                return self._create_no_person_response()
            
            # Step 2: PPE Detection for each person
            ppe_results = []
            total_people = len(person_detections)
            compliant_people = 0
            
            for person_bbox in person_detections:
                person_result = self._analyze_person_ppe(frame, person_bbox, sector)
                ppe_results.append(person_result)
                
                if person_result['compliant']:
                    compliant_people += 1
            
            # Step 3: Calculate overall compliance
            compliance_rate = (compliant_people / total_people * 100) if total_people > 0 else 0
            
            # Step 4: Generate violations list
            violations = self._generate_violations_list(ppe_results)
            
            # Step 5: Performance metrics
            processing_time = datetime.now().timestamp()
            
            result = {
                'success': True,
                'total_people': total_people,
                'compliant_people': compliant_people,
                'compliance_rate': compliance_rate,
                'violations': violations,
                'ppe_results': ppe_results,
                'sector': sector,
                'timestamp': datetime.now().isoformat(),
                'processing_time': processing_time,
                'detection_count': total_people,
                'frame_count': 1
            }
            
            logger.info(f"✅ PPE Detection completed: {compliant_people}/{total_people} compliant ({compliance_rate:.1f}%)")
            return result
            
        except Exception as e:
            logger.error(f"❌ PPE detection error: {e}")
            return self._create_error_response(str(e))
    
    def _detect_persons(self, frame: np.ndarray) -> List[List[int]]:
        """Detect persons in frame"""
        try:
            # Try CUDA first, fallback to CPU if needed
            try:
                results = self.person_model(frame, classes=[0], conf=0.5, verbose=False)  # class 0 = person
            except Exception as cuda_error:
                logger.warning(f"⚠️ CUDA detection failed: {cuda_error}, trying CPU")
                # Force CPU detection
                self.person_model.to('cpu')
                results = self.person_model(frame, classes=[0], conf=0.5, verbose=False)
            
            person_bboxes = []
            
            if results and len(results) > 0:
                for result in results:
                    if result.boxes is not None:
                        for box in result.boxes:
                            if box.conf > 0.5:  # Confidence threshold
                                try:
                                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                    person_bboxes.append([int(x1), int(y1), int(x2), int(y2)])
                                except Exception as box_error:
                                    logger.warning(f"⚠️ Box processing error: {box_error}")
                                    continue
            
            logger.info(f"🔍 Detected {len(person_bboxes)} persons")
            return person_bboxes
            
        except Exception as e:
            logger.error(f"❌ Person detection error: {e}")
            return []
    
    def _analyze_person_ppe(self, frame: np.ndarray, person_bbox: List[int], sector: str) -> Dict[str, Any]:
        """Analyze PPE compliance for a single person"""
        try:
            x1, y1, x2, y2 = person_bbox
            person_roi = frame[y1:y2, x1:x2]
            
            if person_roi.size == 0:
                return self._create_person_error_response("Empty ROI")
            
            # Get required PPE for sector
            required_ppe = self.sector_ppe_mapping.get(sector, self.sector_ppe_mapping['general'])
            
            # Enhanced PPE detection
            detected_ppe = self._detect_ppe_items(person_roi)
            
            # Validate compliance
            missing_ppe = []
            for required in required_ppe:
                if not self._is_ppe_detected(required, detected_ppe):
                    missing_ppe.append(required)
            
            compliant = len(missing_ppe) == 0
            
            return {
                'person_bbox': person_bbox,
                'detected_ppe': detected_ppe,
                'required_ppe': required_ppe,
                'missing_ppe': missing_ppe,
                'compliant': compliant,
                'compliance_score': self._calculate_compliance_score(detected_ppe, required_ppe)
            }
            
        except Exception as e:
            logger.error(f"❌ Person PPE analysis error: {e}")
            return self._create_person_error_response(str(e))
    
    def _detect_ppe_items(self, person_roi: np.ndarray) -> Dict[str, float]:
        """Detect PPE items in person ROI"""
        detected_ppe = {}
        
        try:
            # Enhanced color-based detection
            hsv = cv2.cvtColor(person_roi, cv2.COLOR_BGR2HSV)
            
            # Helmet detection (yellow, white, red, blue)
            helmet_confidence = self._detect_helmet(hsv)
            if helmet_confidence > 0.3:
                detected_ppe['helmet'] = helmet_confidence
            
            # Safety vest detection (orange, yellow, green, blue)
            vest_confidence = self._detect_safety_vest(hsv)
            if vest_confidence > 0.3:
                detected_ppe['safety_vest'] = vest_confidence
            
            # Safety shoes detection (black, brown)
            shoes_confidence = self._detect_safety_shoes(person_roi)
            if shoes_confidence > 0.3:
                detected_ppe['safety_shoes'] = shoes_confidence
            
            # Gloves detection (white, yellow, orange)
            gloves_confidence = self._detect_gloves(hsv)
            if gloves_confidence > 0.3:
                detected_ppe['gloves'] = gloves_confidence
            
            # Respirator detection (white, blue)
            respirator_confidence = self._detect_respirator(person_roi)
            if respirator_confidence > 0.3:
                detected_ppe['respirator'] = respirator_confidence
            
            # Safety glasses detection
            glasses_confidence = self._detect_safety_glasses(person_roi)
            if glasses_confidence > 0.3:
                detected_ppe['safety_glasses'] = glasses_confidence
            
        except Exception as e:
            logger.error(f"❌ PPE item detection error: {e}")
        
        return detected_ppe
    
    def _detect_helmet(self, hsv: np.ndarray) -> float:
        """Detect helmet using color analysis"""
        try:
            # Yellow helmet
            yellow_lower = np.array([20, 100, 100])
            yellow_upper = np.array([30, 255, 255])
            yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
            
            # White helmet
            white_lower = np.array([0, 0, 200])
            white_upper = np.array([180, 30, 255])
            white_mask = cv2.inRange(hsv, white_lower, white_upper)
            
            # Red helmet
            red_lower1 = np.array([0, 100, 100])
            red_upper1 = np.array([10, 255, 255])
            red_lower2 = np.array([170, 100, 100])
            red_upper2 = np.array([180, 255, 255])
            red_mask1 = cv2.inRange(hsv, red_lower1, red_upper1)
            red_mask2 = cv2.inRange(hsv, red_lower2, red_upper2)
            red_mask = cv2.bitwise_or(red_mask1, red_mask2)
            
            # Blue helmet
            blue_lower = np.array([100, 100, 100])
            blue_upper = np.array([130, 255, 255])
            blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
            
            # Combine all helmet masks
            helmet_mask = cv2.bitwise_or(yellow_mask, white_mask)
            helmet_mask = cv2.bitwise_or(helmet_mask, red_mask)
            helmet_mask = cv2.bitwise_or(helmet_mask, blue_mask)
            
            # Calculate confidence
            total_pixels = hsv.shape[0] * hsv.shape[1]
            helmet_pixels = cv2.countNonZero(helmet_mask)
            confidence = helmet_pixels / total_pixels if total_pixels > 0 else 0
            
            return min(confidence * 5, 1.0)  # Scale confidence
            
        except Exception as e:
            logger.error(f"❌ Helmet detection error: {e}")
            return 0.0
    
    def _detect_safety_vest(self, hsv: np.ndarray) -> float:
        """Detect safety vest using color analysis"""
        try:
            # Orange vest
            orange_lower = np.array([10, 100, 100])
            orange_upper = np.array([20, 255, 255])
            orange_mask = cv2.inRange(hsv, orange_lower, orange_upper)
            
            # Yellow vest
            yellow_lower = np.array([20, 100, 100])
            yellow_upper = np.array([30, 255, 255])
            yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
            
            # Green vest
            green_lower = np.array([40, 100, 100])
            green_upper = np.array([80, 255, 255])
            green_mask = cv2.inRange(hsv, green_lower, green_upper)
            
            # Blue vest
            blue_lower = np.array([100, 100, 100])
            blue_upper = np.array([130, 255, 255])
            blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
            
            # Combine all vest masks
            vest_mask = cv2.bitwise_or(orange_mask, yellow_mask)
            vest_mask = cv2.bitwise_or(vest_mask, green_mask)
            vest_mask = cv2.bitwise_or(vest_mask, blue_mask)
            
            # Calculate confidence
            total_pixels = hsv.shape[0] * hsv.shape[1]
            vest_pixels = cv2.countNonZero(vest_mask)
            confidence = vest_pixels / total_pixels if total_pixels > 0 else 0
            
            return min(confidence * 3, 1.0)  # Scale confidence
            
        except Exception as e:
            logger.error(f"❌ Safety vest detection error: {e}")
            return 0.0
    
    def _detect_safety_shoes(self, person_roi: np.ndarray) -> float:
        """Detect safety shoes"""
        try:
            # Convert to different color spaces for better detection
            hsv = cv2.cvtColor(person_roi, cv2.COLOR_BGR2HSV)
            
            # Black shoes
            black_lower = np.array([0, 0, 0])
            black_upper = np.array([180, 255, 50])
            black_mask = cv2.inRange(hsv, black_lower, black_upper)
            
            # Brown shoes
            brown_lower = np.array([10, 50, 50])
            brown_upper = np.array([20, 255, 200])
            brown_mask = cv2.inRange(hsv, brown_lower, brown_upper)
            
            # Combine masks
            shoes_mask = cv2.bitwise_or(black_mask, brown_mask)
            
            # Focus on lower part of person (feet area)
            height, width = person_roi.shape[:2]
            feet_region = person_roi[int(height*0.7):height, :]
            feet_mask = shoes_mask[int(height*0.7):height, :]
            
            # Calculate confidence
            total_pixels = feet_region.shape[0] * feet_region.shape[1]
            shoes_pixels = cv2.countNonZero(feet_mask)
            confidence = shoes_pixels / total_pixels if total_pixels > 0 else 0
            
            return min(confidence * 2, 1.0)
            
        except Exception as e:
            logger.error(f"❌ Safety shoes detection error: {e}")
            return 0.0
    
    def _detect_gloves(self, hsv: np.ndarray) -> float:
        """Detect gloves"""
        try:
            # White gloves
            white_lower = np.array([0, 0, 200])
            white_upper = np.array([180, 30, 255])
            white_mask = cv2.inRange(hsv, white_lower, white_upper)
            
            # Yellow gloves
            yellow_lower = np.array([20, 100, 100])
            yellow_upper = np.array([30, 255, 255])
            yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
            
            # Orange gloves
            orange_lower = np.array([10, 100, 100])
            orange_upper = np.array([20, 255, 255])
            orange_mask = cv2.inRange(hsv, orange_lower, orange_upper)
            
            # Combine masks
            gloves_mask = cv2.bitwise_or(white_mask, yellow_mask)
            gloves_mask = cv2.bitwise_or(gloves_mask, orange_mask)
            
            # Calculate confidence
            total_pixels = hsv.shape[0] * hsv.shape[1]
            gloves_pixels = cv2.countNonZero(gloves_mask)
            confidence = gloves_pixels / total_pixels if total_pixels > 0 else 0
            
            return min(confidence * 4, 1.0)
            
        except Exception as e:
            logger.error(f"❌ Gloves detection error: {e}")
            return 0.0
    
    def _detect_respirator(self, person_roi: np.ndarray) -> float:
        """Detect respirator"""
        try:
            hsv = cv2.cvtColor(person_roi, cv2.COLOR_BGR2HSV)
            
            # White respirator
            white_lower = np.array([0, 0, 200])
            white_upper = np.array([180, 30, 255])
            white_mask = cv2.inRange(hsv, white_lower, white_upper)
            
            # Blue respirator
            blue_lower = np.array([100, 100, 100])
            blue_upper = np.array([130, 255, 255])
            blue_mask = cv2.inRange(hsv, blue_lower, blue_upper)
            
            # Combine masks
            respirator_mask = cv2.bitwise_or(white_mask, blue_mask)
            
            # Focus on face area
            height, width = person_roi.shape[:2]
            face_region = person_roi[int(height*0.1):int(height*0.4), :]
            face_mask = respirator_mask[int(height*0.1):int(height*0.4), :]
            
            # Calculate confidence
            total_pixels = face_region.shape[0] * face_region.shape[1]
            respirator_pixels = cv2.countNonZero(face_mask)
            confidence = respirator_pixels / total_pixels if total_pixels > 0 else 0
            
            return min(confidence * 3, 1.0)
            
        except Exception as e:
            logger.error(f"❌ Respirator detection error: {e}")
            return 0.0
    
    def _detect_safety_glasses(self, person_roi: np.ndarray) -> float:
        """Detect safety glasses"""
        try:
            # Focus on face area
            height, width = person_roi.shape[:2]
            face_region = person_roi[int(height*0.1):int(height*0.4), :]
            
            # Convert to grayscale for edge detection
            gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # Look for circular/rectangular patterns (glasses frames)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            glasses_confidence = 0.0
            for contour in contours:
                area = cv2.contourArea(contour)
                if 100 < area < 2000:  # Reasonable size for glasses
                    # Check if contour is roughly rectangular
                    x, y, w, h = cv2.boundingRect(contour)
                    aspect_ratio = w / h if h > 0 else 0
                    if 0.5 < aspect_ratio < 2.0:  # Reasonable aspect ratio
                        glasses_confidence += 0.2
            
            return min(glasses_confidence, 1.0)
            
        except Exception as e:
            logger.error(f"❌ Safety glasses detection error: {e}")
            return 0.0
    
    def _is_ppe_detected(self, required_ppe: str, detected_ppe: Dict[str, float]) -> bool:
        """Check if required PPE is detected"""
        return required_ppe in detected_ppe and detected_ppe[required_ppe] > 0.3
    
    def _calculate_compliance_score(self, detected_ppe: Dict[str, float], required_ppe: List[str]) -> float:
        """Calculate compliance score"""
        if not required_ppe:
            return 1.0
        
        detected_count = sum(1 for ppe in required_ppe if self._is_ppe_detected(ppe, detected_ppe))
        return detected_count / len(required_ppe)
    
    def _generate_violations_list(self, ppe_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate violations list from PPE results"""
        violations = []
        
        for i, result in enumerate(ppe_results):
            if not result['compliant']:
                violation = {
                    'person_id': f'Person_{i+1}',
                    'missing_ppe': result['missing_ppe'],
                    'detected_ppe': list(result['detected_ppe'].keys()),
                    'compliance_score': result['compliance_score'],
                    'timestamp': datetime.now().isoformat()
                }
                violations.append(violation)
        
        return violations
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response"""
        return {
            'success': False,
            'error': error_message,
            'total_people': 0,
            'compliant_people': 0,
            'compliance_rate': 0,
            'violations': [],
            'timestamp': datetime.now().isoformat()
        }
    
    def _create_no_person_response(self) -> Dict[str, Any]:
        """Create response when no persons detected"""
        return {
            'success': True,
            'total_people': 0,
            'compliant_people': 0,
            'compliance_rate': 0,
            'violations': [],
            'timestamp': datetime.now().isoformat(),
            'message': 'No persons detected'
        }
    
    def _create_person_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create person analysis error response"""
        return {
            'person_bbox': [],
            'detected_ppe': {},
            'required_ppe': [],
            'missing_ppe': [],
            'compliant': False,
            'compliance_score': 0.0,
            'error': error_message
        }
    
    def get_sector_requirements(self, sector: str) -> List[str]:
        """Get PPE requirements for a sector"""
        return self.sector_ppe_mapping.get(sector, self.sector_ppe_mapping['general'])
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        return self.performance_metrics 