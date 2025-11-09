"""
🎯 POSE-AWARE PPE DETECTION SYSTEM
===================================
Production-grade PPE detection with human pose estimation

PHASES:
- Phase 1: Human-Centric PPE Detection ✅
- Phase 2: Anatomical PPE Localization ✅
- Phase 3: Pose-Aware PPE Detection ⚡ (THIS MODULE)
- Phase 4: Full Compliance Monitoring 🚀

Features:
- YOLOv8-Pose integration for keypoint detection
- Anatomical region mapping using pose keypoints
- Enhanced PPE-person association
- Pose-based compliance scoring
- Real-time performance optimization
"""

import cv2
import numpy as np
import os
from typing import Dict, List, Optional, Tuple
import logging
import time

logger = logging.getLogger(__name__)


class PoseAwarePPEDetector:
    """
    Pose-aware PPE detection using YOLOv8-Pose keypoints
    
    Keypoint indices (COCO format):
    0: Nose, 1-2: Eyes, 3-4: Ears, 5-6: Shoulders,
    7-8: Elbows, 9-10: Wrists, 11-12: Hips,
    13-14: Knees, 15-16: Ankles
    """
    
    def __init__(self, pose_model_path: Optional[str] = None, ppe_detector=None):
        """
        Initialize pose-aware PPE detector
        
        Args:
            pose_model_path: Path to YOLOv8-Pose model (optional, will download if not provided)
            ppe_detector: Existing PPE detector instance (SH17ModelManager)
        """
        self.pose_model = None
        self.ppe_detector = ppe_detector
        self.pose_confidence_threshold = 0.5
        self.keypoint_confidence_threshold = 0.3
        
        # 🎯 KEYPOINT SMOOTHING - Stabilize detection across frames
        self.prev_keypoints = {}  # Store previous frame keypoints per person
        self.keypoint_smoothing_factor = 0.6  # 60% previous, 40% current
        
        # Load YOLOv8-Pose model
        self._load_pose_model(pose_model_path)
        
        logger.info("✅ Pose-Aware PPE Detector initialized")
    
    def _load_pose_model(self, model_path: Optional[str] = None):
        """Load YOLOv8-Pose model with CPU inference to avoid CUDA NMS issues"""
        try:
            from ultralytics import YOLO
            
            if model_path and os.path.exists(model_path):
                self.pose_model = YOLO(model_path)
                logger.info(f"✅ Loaded custom pose model: {model_path}")
            else:
                # Download YOLOv8n-Pose (lightweight, fast)
                self.pose_model = YOLO('yolov8n-pose.pt')
                logger.info("✅ Loaded YOLOv8n-Pose (auto-downloaded)")
            
            # 🔧 FIX: Force CPU inference to avoid CUDA torchvision::nms incompatibility
            # This is a known issue where torchvision.ops.nms doesn't support CUDA backend
            # CPU inference works perfectly fine and is still fast with yolov8n-pose
            self.pose_model.to('cpu')
            logger.info("🔧 Pose model set to CPU inference (CUDA NMS compatibility fix)")
                
        except ImportError:
            logger.warning("⚠️ Ultralytics not installed. Install with: pip install ultralytics")
            logger.warning("⚠️ Falling back to anatomical detection without pose")
        except Exception as e:
            logger.error(f"❌ Failed to load pose model: {e}")
            logger.warning("⚠️ Falling back to anatomical detection without pose")
    
    def detect_with_pose(self, frame: np.ndarray, sector: Optional[str] = None, 
                        confidence: float = 0.25) -> Dict:
        """
        Perform pose-aware PPE detection
        
        Args:
            frame: Input video frame
            sector: Sector type for PPE requirements
            confidence: Detection confidence threshold
            
        Returns:
            Detection result with pose-enhanced PPE associations
        """
        if self.pose_model is None:
            logger.warning("⚠️ Pose model not available, using standard detection")
            if self.ppe_detector:
                return self.ppe_detector.detect_ppe(frame, sector, confidence)
            return self._create_empty_result()
        
        try:
            start_time = time.time()
            
            # 🔧 Ensure frame is on CPU for model inference
            if isinstance(frame, np.ndarray):
                frame_for_inference = frame.copy()
            else:
                frame_for_inference = frame
            
            # 1️⃣ Detect poses (persons with keypoints) - CPU inference
            pose_results = self.pose_model(frame_for_inference, conf=self.pose_confidence_threshold, verbose=False, device='cpu')
            
            # 2️⃣ Detect PPE items (using existing detector)
            ppe_detections = []
            if self.ppe_detector:
                ppe_result = self.ppe_detector.detect_ppe(frame, sector, confidence)
                if isinstance(ppe_result, list):
                    ppe_detections = ppe_result
                elif isinstance(ppe_result, dict):
                    ppe_detections = ppe_result.get('detections', [])
            
            # 3️⃣ Extract pose data
            persons_with_pose = self._extract_pose_data(pose_results, frame.shape)
            
            # 🔍 FALLBACK CHECK - If no persons detected, use standard detection
            if not persons_with_pose:
                logger.warning("⚠️ No persons detected with pose, falling back to standard detection")
                if self.ppe_detector:
                    return self.ppe_detector.detect_ppe(frame, sector, confidence)
                return self._create_empty_result()
            
            # 4️⃣ Associate PPE with persons using pose keypoints
            enhanced_detections = self._associate_ppe_with_pose(
                persons_with_pose, ppe_detections, frame.shape
            )
            
            # 5️⃣ Calculate compliance with pose-aware scoring
            compliance_result = self._calculate_pose_aware_compliance(
                enhanced_detections, sector
            )
            
            # 🔍 QUALITY CHECK - If compliance is 0% and we have people, might be detection issue
            if compliance_result['people_detected'] > 0 and compliance_result['compliance_rate'] == 0:
                logger.warning(f"⚠️ 0% compliance detected for {compliance_result['people_detected']} people - checking quality")
                # Log for debugging
                logger.debug(f"PPE detections available: {len(ppe_detections)}")
                logger.debug(f"Persons with pose: {len(persons_with_pose)}")
            
            elapsed = time.time() - start_time
            logger.info(f"⚡ Pose-aware detection: {len(persons_with_pose)} persons, "
                       f"{compliance_result['compliance_rate']}% compliance ({elapsed:.3f}s)")
            
            return compliance_result
            
        except Exception as e:
            logger.error(f"❌ Pose-aware detection failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            logger.warning("⚠️ Falling back to standard detection after pose error")
            # FALLBACK: Use standard detection if pose fails
            if self.ppe_detector:
                return self.ppe_detector.detect_ppe(frame, sector, confidence)
            return self._create_empty_result()
    
    def _smooth_keypoints(self, keypoints: List[Dict], person_id: int) -> List[Dict]:
        """
        Smooth keypoints across frames to reduce jitter
        Uses exponential moving average
        """
        if person_id not in self.prev_keypoints:
            self.prev_keypoints[person_id] = keypoints
            return keypoints
        
        prev_kpts = self.prev_keypoints[person_id]
        smoothed_kpts = []
        
        for curr_kpt in keypoints:
            idx = curr_kpt['index']
            
            # Find corresponding previous keypoint
            prev_kpt = next((k for k in prev_kpts if k['index'] == idx), None)
            
            if prev_kpt and prev_kpt.get('confidence', 0) > 0.1:
                # Smooth position using exponential moving average
                smoothed_x = (prev_kpt['x'] * self.keypoint_smoothing_factor + 
                             curr_kpt['x'] * (1 - self.keypoint_smoothing_factor))
                smoothed_y = (prev_kpt['y'] * self.keypoint_smoothing_factor + 
                             curr_kpt['y'] * (1 - self.keypoint_smoothing_factor))
                
                smoothed_kpts.append({
                    'index': idx,
                    'x': smoothed_x,
                    'y': smoothed_y,
                    'confidence': max(prev_kpt.get('confidence', 0), curr_kpt.get('confidence', 0))
                })
            else:
                # No previous keypoint, use current as-is
                smoothed_kpts.append(curr_kpt)
        
        # Store for next frame
        self.prev_keypoints[person_id] = smoothed_kpts
        
        logger.debug(f"🎯 Smoothed keypoints for person {person_id}")
        return smoothed_kpts
    
    def _extract_pose_data(self, pose_results, frame_shape: Tuple[int, int, int]) -> List[Dict]:
        """Extract person bounding boxes and keypoints from pose results"""
        persons = []
        
        try:
            for result in pose_results:
                if result.keypoints is None:
                    continue
                
                # Get bounding boxes and keypoints
                boxes = result.boxes.xyxy.cpu().numpy() if result.boxes is not None else []
                keypoints = result.keypoints.xy.cpu().numpy() if result.keypoints is not None else []
                confidences = result.keypoints.conf.cpu().numpy() if result.keypoints is not None else []
                
                for i, (box, kpts, kpt_conf) in enumerate(zip(boxes, keypoints, confidences)):
                    x1, y1, x2, y2 = box
                    
                    # 🔧 STRICT BBOX CLIPPING - Ensure person bbox stays within frame
                    frame_height, frame_width = frame_shape[:2]
                    x1 = max(0, min(x1, frame_width - 1))
                    x2 = max(x1 + 1, min(x2, frame_width))
                    y1 = max(0, min(y1, frame_height - 1))
                    y2 = max(y1 + 1, min(y2, frame_height))
                    
                    # Extract keypoints with confidence
                    keypoint_data = []
                    for j, (kpt, conf) in enumerate(zip(kpts, kpt_conf)):
                        if conf > self.keypoint_confidence_threshold:
                            keypoint_data.append({
                                'index': j,
                                'x': float(kpt[0]),
                                'y': float(kpt[1]),
                                'confidence': float(conf)
                            })
                    
                    # 🎯 SMOOTH KEYPOINTS - Reduce jitter across frames
                    person_id = i  # Use index as person ID for this frame
                    keypoint_data = self._smooth_keypoints(keypoint_data, person_id)
                    
                    # Calculate anatomical regions from keypoints
                    anatomical_regions = self._calculate_anatomical_regions_from_pose(
                        keypoint_data, (x1, y1, x2, y2), frame_shape
                    )
                    
                    persons.append({
                        'bbox': [float(x1), float(y1), float(x2), float(y2)],
                        'keypoints': keypoint_data,
                        'anatomical_regions': anatomical_regions,
                        'class_name': 'person',
                        'confidence': float(result.boxes.conf[i]) if result.boxes is not None else 0.9
                    })
            
            logger.debug(f"📊 Extracted {len(persons)} persons with pose data")
            return persons
            
        except Exception as e:
            logger.error(f"❌ Pose extraction failed: {e}")
            return []
    
    def _calculate_anatomical_regions_from_pose(self, keypoints: List[Dict], 
                                               person_bbox: Tuple, 
                                               frame_shape: Tuple) -> Dict:
        """
        Calculate precise anatomical regions using pose keypoints with strict frame clipping
        
        Regions:
        - head: nose, eyes, ears
        - torso: shoulders, hips
        - feet: ankles
        """
        frame_height, frame_width = frame_shape[:2]
        px1, py1, px2, py2 = person_bbox
        
        # 🔧 STRICT CLIPPING HELPER - Ensures bbox never exceeds frame
        def clip_bbox(x1, y1, x2, y2):
            """Clip bbox to frame boundaries with safety checks"""
            x1 = max(0, min(x1, frame_width - 1))
            x2 = max(x1 + 1, min(x2, frame_width))
            y1 = max(0, min(y1, frame_height - 1))
            y2 = max(y1 + 1, min(y2, frame_height))
            return [x1, y1, x2, y2]
        
        # Create keypoint lookup
        kpt_dict = {kpt['index']: kpt for kpt in keypoints}
        
        # Helper to get keypoint or None
        def get_kpt(idx):
            return kpt_dict.get(idx)
        
        # 🎯 HEAD REGION - Using facial keypoints
        head_region = None
        nose = get_kpt(0)
        left_eye = get_kpt(1)
        right_eye = get_kpt(2)
        left_ear = get_kpt(3)
        right_ear = get_kpt(4)
        
        head_points = [p for p in [nose, left_eye, right_eye, left_ear, right_ear] if p]
        if head_points:
            head_xs = [p['x'] for p in head_points]
            head_ys = [p['y'] for p in head_points]
            
            # Filter keypoints that are within frame bounds
            valid_xs = [x for x in head_xs if 0 <= x < frame_width]
            valid_ys = [y for y in head_ys if 0 <= y < frame_height]
            
            if valid_xs and valid_ys:
                # Expand head region (helmet is larger than head)
                head_width = max(valid_xs) - min(valid_xs)
                head_height = max(valid_ys) - min(valid_ys)
                
                # Use person bbox as fallback if keypoints are too sparse
                if head_width < 5:
                    head_width = (px2 - px1) * 0.4
                if head_height < 5:
                    head_height = (py2 - py1) * 0.25
                
                head_x1 = min(valid_xs) - head_width * 0.3
                head_x2 = max(valid_xs) + head_width * 0.3
                head_y1 = min(valid_ys) - head_height * 0.5  # Extend up for helmet
                head_y2 = max(valid_ys) + head_height * 0.2
                
                head_region = clip_bbox(head_x1, head_y1, head_x2, head_y2)
        
        # 🎯 TORSO REGION - Using shoulders and hips
        torso_region = None
        left_shoulder = get_kpt(5)
        right_shoulder = get_kpt(6)
        left_hip = get_kpt(11)
        right_hip = get_kpt(12)
        
        torso_points = [p for p in [left_shoulder, right_shoulder, left_hip, right_hip] if p]
        if torso_points:
            torso_xs = [p['x'] for p in torso_points]
            torso_ys = [p['y'] for p in torso_points]
            
            # Filter keypoints that are within frame bounds
            valid_xs = [x for x in torso_xs if 0 <= x < frame_width]
            valid_ys = [y for y in torso_ys if 0 <= y < frame_height]
            
            if valid_xs and valid_ys:
                # Expand for vest coverage
                torso_width = max(valid_xs) - min(valid_xs)
                
                if torso_width < 5:
                    torso_width = (px2 - px1) * 0.5
                
                torso_x1 = min(valid_xs) - torso_width * 0.2
                torso_x2 = max(valid_xs) + torso_width * 0.2
                torso_y1 = min(valid_ys)
                torso_y2 = max(valid_ys)
                
                torso_region = clip_bbox(torso_x1, torso_y1, torso_x2, torso_y2)
        
        # 🎯 FEET REGION - Using ankles
        feet_region = None
        left_ankle = get_kpt(15)
        right_ankle = get_kpt(16)
        
        ankle_points = [p for p in [left_ankle, right_ankle] if p]
        if ankle_points:
            ankle_xs = [p['x'] for p in ankle_points]
            ankle_ys = [p['y'] for p in ankle_points]
            
            # Filter keypoints that are within frame bounds
            valid_xs = [x for x in ankle_xs if 0 <= x < frame_width]
            valid_ys = [y for y in ankle_ys if 0 <= y < frame_height]
            
            if valid_xs and valid_ys:
                # Expand for shoe coverage
                feet_width = max(valid_xs) - min(valid_xs) if len(valid_xs) > 1 else (px2 - px1) * 0.3
                
                if feet_width < 5:
                    feet_width = (px2 - px1) * 0.3
                
                feet_x1 = min(valid_xs) - feet_width * 0.5
                feet_x2 = max(valid_xs) + feet_width * 0.5
                feet_y1 = min(valid_ys) - 20  # Extend up slightly
                feet_y2 = py2  # Bottom of person bbox
                
                feet_region = clip_bbox(feet_x1, feet_y1, feet_x2, feet_y2)
        
        # Fallback to geometric regions if keypoints missing
        if head_region is None:
            person_width = px2 - px1
            person_height = py2 - py1
            head_width = person_width * 0.40
            person_center_x = (px1 + px2) / 2
            head_x1 = max(0, person_center_x - head_width / 2)
            head_x2 = min(frame_width, person_center_x + head_width / 2)
            head_y1 = max(0, py1)
            head_y2 = min(frame_height, py1 + person_height * 0.24)
            head_region = [head_x1, head_y1, head_x2, head_y2]
        
        if torso_region is None:
            person_width = px2 - px1
            person_height = py2 - py1
            torso_width = person_width * 0.70
            person_center_x = (px1 + px2) / 2
            torso_x1 = max(0, person_center_x - torso_width / 2)
            torso_x2 = min(frame_width, person_center_x + torso_width / 2)
            torso_y1 = max(0, py1 + person_height * 0.20)
            torso_y2 = min(frame_height, py1 + person_height * 0.65)
            torso_region = [torso_x1, torso_y1, torso_x2, torso_y2]
        
        if feet_region is None:
            person_width = px2 - px1
            person_height = py2 - py1
            foot_width = person_width * 0.5
            person_center_x = (px1 + px2) / 2
            feet_x1 = max(0, person_center_x - foot_width / 2)
            feet_x2 = min(frame_width, person_center_x + foot_width / 2)
            feet_y1 = max(0, py2 - person_height * 0.15)
            feet_y2 = min(frame_height, py2)
            feet_region = [feet_x1, feet_y1, feet_x2, feet_y2]
        
        return {
            'head': head_region,
            'torso': torso_region,
            'feet': feet_region
        }
    
    def _associate_ppe_with_pose(self, persons: List[Dict], ppe_detections: List[Dict],
                                frame_shape: Tuple) -> List[Dict]:
        """Associate PPE items with persons using pose-based anatomical regions"""
        
        # Separate PPE by type (with multiple class name variations)
        helmets = [d for d in ppe_detections if any(x in d.get('class_name', '').lower() 
                  for x in ['helmet', 'hard_hat', 'hardhat', 'baret'])
                  and not d.get('class_name', '').startswith('NO-')]
        vests = [d for d in ppe_detections if any(x in d.get('class_name', '').lower() 
                for x in ['vest', 'safety_vest', 'yelek'])
                and not d.get('class_name', '').startswith('NO-')]
        shoes = [d for d in ppe_detections if any(x in d.get('class_name', '').lower() 
                for x in ['shoe', 'shoes', 'safety_shoes', 'ayakkabı', 'ayakkabi'])
                and not d.get('class_name', '').startswith('NO-')]
        
        logger.debug(f"🔍 PPE separation: {len(helmets)} helmets, {len(vests)} vests, {len(shoes)} shoes")
        
        enhanced_persons = []
        
        for person in persons:
            regions = person['anatomical_regions']
            person_bbox = person['bbox']
            
            # Find best matching PPE for each region (with type-specific thresholds)
            best_helmet = self._find_best_ppe_match(helmets, regions['head'], person_bbox, 'helmet')
            best_vest = self._find_best_ppe_match(vests, regions['torso'], person_bbox, 'vest')
            best_shoes = self._find_best_ppe_match(shoes, regions['feet'], person_bbox, 'shoes')
            
            # Build enhanced person data
            enhanced_person = {
                'person': person,
                'ppe': {
                    'helmet': best_helmet,
                    'vest': best_vest,
                    'shoes': best_shoes
                },
                'regions': regions,
                'compliance': {
                    'has_helmet': best_helmet is not None,
                    'has_vest': best_vest is not None,
                    'has_shoes': best_shoes is not None
                }
            }
            
            enhanced_persons.append(enhanced_person)
        
        return enhanced_persons
    
    def _find_best_ppe_match(self, ppe_items: List[Dict], region: List[float], 
                            person_bbox: List[float], ppe_type: str = 'general') -> Optional[Dict]:
        """Find best PPE match for anatomical region using IoU with type-specific thresholds"""
        best_match = None
        best_iou = 0.0
        
        # Type-specific thresholds (shoes need lower threshold due to occlusion)
        iou_threshold = {
            'helmet': 0.05,
            'vest': 0.05,
            'shoes': 0.02,  # Lower for shoes - often partially visible
            'general': 0.05
        }.get(ppe_type, 0.05)
        
        person_iou_threshold = {
            'helmet': 0.1,
            'vest': 0.1,
            'shoes': 0.05,  # Lower for shoes
            'general': 0.1
        }.get(ppe_type, 0.1)
        
        for ppe in ppe_items:
            ppe_bbox = ppe.get('bbox', [])
            if len(ppe_bbox) != 4:
                continue
            
            iou = self._calculate_iou(ppe_bbox, region)
            
            # Also check if PPE is within person bbox (sanity check)
            person_iou = self._calculate_iou(ppe_bbox, person_bbox)
            
            if iou > best_iou and person_iou > person_iou_threshold:  # Must overlap with person
                best_iou = iou
                best_match = ppe
        
        return best_match if best_iou > iou_threshold else None
    
    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        """Calculate Intersection over Union"""
        try:
            x1_1, y1_1, x2_1, y2_1 = box1
            x1_2, y1_2, x2_2, y2_2 = box2
            
            # Intersection
            x1_i = max(x1_1, x1_2)
            y1_i = max(y1_1, y1_2)
            x2_i = min(x2_1, x2_2)
            y2_i = min(y2_1, y2_2)
            
            if x2_i <= x1_i or y2_i <= y1_i:
                return 0.0
            
            intersection = (x2_i - x1_i) * (y2_i - y1_i)
            
            # Union
            area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
            area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
            union = area1 + area2 - intersection
            
            return intersection / max(union, 1e-6)
        except:
            return 0.0
    
    def _calculate_pose_aware_compliance(self, enhanced_persons: List[Dict], 
                                        sector: Optional[str]) -> Dict:
        """Calculate compliance with pose-aware scoring"""
        
        total_people = len(enhanced_persons)
        compliant_people = 0
        violations = []
        all_detections = []
        
        for person_data in enhanced_persons:
            person = person_data['person']
            ppe = person_data['ppe']
            regions = person_data['regions']
            compliance = person_data['compliance']
            
            # Add person detection
            all_detections.append(person)
            
            # Add PPE detections with anatomical regions
            if ppe['helmet']:
                all_detections.append({
                    'bbox': regions['head'],
                    'class_name': 'Helmet',
                    'confidence': ppe['helmet'].get('confidence', 0.9),
                    'missing': False,
                    'pose_based': True
                })
            else:
                violations.append('Baret eksik')
                all_detections.append({
                    'bbox': regions['head'],
                    'class_name': 'NO-Helmet',
                    'confidence': 0.9,
                    'missing': True,
                    'pose_based': True
                })
            
            if ppe['vest']:
                all_detections.append({
                    'bbox': regions['torso'],
                    'class_name': 'Safety Vest',
                    'confidence': ppe['vest'].get('confidence', 0.9),
                    'missing': False,
                    'pose_based': True
                })
            else:
                violations.append('Yelek eksik')
                all_detections.append({
                    'bbox': regions['torso'],
                    'class_name': 'NO-Vest',
                    'confidence': 0.9,
                    'missing': True,
                    'pose_based': True
                })
            
            if ppe['shoes']:
                all_detections.append({
                    'bbox': regions['feet'],
                    'class_name': 'Safety Shoes',
                    'confidence': ppe['shoes'].get('confidence', 0.9),
                    'missing': False,
                    'pose_based': True
                })
            else:
                violations.append('Güvenlik ayakkabısı eksik')
                all_detections.append({
                    'bbox': regions['feet'],
                    'class_name': 'NO-Shoes',
                    'confidence': 0.9,
                    'missing': True,
                    'pose_based': True
                })
            
            # Check compliance (minimum: helmet + vest)
            if compliance['has_helmet'] and compliance['has_vest']:
                compliant_people += 1
        
        compliance_rate = int((compliant_people / max(total_people, 1)) * 100) if total_people > 0 else 100
        
        return {
            'detections': all_detections,
            'people_detected': total_people,
            'compliance_rate': compliance_rate,
            'ppe_violations': list(set(violations)),
            'timestamp': time.time(),
            'sector': sector,
            'model_type': 'YOLOv8-Pose + SH17',
            'total_people': total_people,
            'compliant_people': compliant_people,
            'violations_count': len(set(violations)),
            'pose_enhanced': True
        }
    
    def _create_empty_result(self) -> Dict:
        """Create empty detection result"""
        return {
            'detections': [],
            'people_detected': 0,
            'compliance_rate': 100,
            'ppe_violations': [],
            'timestamp': time.time(),
            'sector': None,
            'model_type': 'Fallback',
            'total_people': 0,
            'compliant_people': 0,
            'violations_count': 0,
            'pose_enhanced': False
        }


# Singleton instance
_pose_detector_instance = None


def get_pose_aware_detector(ppe_detector=None) -> PoseAwarePPEDetector:
    """Get singleton pose-aware detector instance"""
    global _pose_detector_instance
    if _pose_detector_instance is None:
        _pose_detector_instance = PoseAwarePPEDetector(ppe_detector=ppe_detector)
    return _pose_detector_instance


if __name__ == "__main__":
    # Test pose-aware detection
    import os
    
    logger.info("🧪 Testing Pose-Aware PPE Detector")
    
    detector = get_pose_aware_detector()
    
    # Test with sample image (if available)
    test_image_path = "test_image.jpg"
    if os.path.exists(test_image_path):
        frame = cv2.imread(test_image_path)
        result = detector.detect_with_pose(frame)
        logger.info(f"✅ Test result: {result['people_detected']} people, "
                   f"{result['compliance_rate']}% compliance")
    else:
        logger.info("⚠️ No test image found, skipping test")
