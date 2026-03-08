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
from collections import deque
import logging
import time

logger = logging.getLogger(__name__)

try:
    import torch
except ImportError:
    torch = None

try:
    import supervision as sv
except ImportError:
    sv = None
    logger.warning("supervision library is not installed. ByteTrack tracking will be disabled.")

# Kanonik PPE tanımları: model sınıf adları, anatomik bölge ve overlay/ihlal etiketleri
PPE_CONFIG = {
    'helmet': {
        'model_classes': ['helmet', 'hard_hat', 'hardhat', 'baret'],
        'region': 'head',
        'pos_label': 'Helmet',
        'neg_label': 'NO-Helmet',
        'violation_tr': 'Baret eksik',
        'default_critical': True,
    },
    'safety_vest': {
        'model_classes': ['safety_vest', 'vest', 'yelek'],
        'region': 'torso',
        'pos_label': 'Safety Vest',
        'neg_label': 'NO-Vest',
        'violation_tr': 'Yelek eksik',
        'default_critical': True,
    },
    'safety_shoes': {
        'model_classes': ['safety_shoes', 'shoes', 'shoe', 'ayakkabı', 'ayakkabi'],
        'region': 'feet',
        'pos_label': 'Safety Shoes',
        'neg_label': 'NO-Shoes',
        'violation_tr': 'Güvenlik ayakkabısı eksik',
        'default_critical': True,
    },
    'gloves': {
        'model_classes': ['gloves'],
        'region': 'hands',
        'pos_label': 'Gloves',
        'neg_label': 'NO-Gloves',
        'violation_tr': 'Eldiven eksik',
        'default_critical': False,
    },
    'safety_glasses': {
        'model_classes': ['safety_glasses', 'glasses'],
        'region': 'head',
        'pos_label': 'Safety Glasses',
        'neg_label': 'NO-Glasses',
        'violation_tr': 'Gözlük eksik',
        'default_critical': False,
    },
    'face_mask': {
        'model_classes': ['face_mask_medical', 'face_mask', 'mask'],
        'region': 'head',
        'pos_label': 'Face Mask',
        'neg_label': 'NO-Mask',
        'violation_tr': 'Maske eksik',
        'default_critical': False,
    },
    'safety_suit': {
        'model_classes': ['safety_suit', 'medical_suit', 'apron'],
        'region': 'torso',
        'pos_label': 'Safety Suit',
        'neg_label': 'NO-Suit',
        'violation_tr': 'Koruyucu tulum eksik',
        'default_critical': False,
    },
}


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
        
        # Keypoint smoothing - stabilize detection across frames
        self.prev_keypoints = {}  # Store previous frame keypoints per tracked person
        self.keypoint_smoothing_factor = 0.6  # 60% previous, 40% current

        # Optional ByteTrack-based person tracker (single instance per detector)
        self.byte_tracker = None
        if sv is not None:
            try:
                # Default parameters are usually sufficient; can be tuned later if needed
                self.byte_tracker = sv.ByteTrack()
                logger.info("ByteTrack tracker initialized for pose-aware detector.")
            except Exception as tracker_error:
                logger.warning(f"Failed to initialize ByteTrack tracker: {tracker_error}")
                self.byte_tracker = None

        # Temporal compliance history per tracked person
        self.compliance_history: Dict[int, deque] = {}
        self.temporal_window_size: int = 15
        self.temporal_required_positive: int = 10
        
        # SH17 PPE detection cadence (every Nth frame). Default: every frame.
        self.sh17_every_n: int = 1
        self._frame_counter: int = 0
        self._last_ppe_detections: List[Dict] = []
        
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
                # Download or load YOLOv8n-Pose from 'core' directory
                pose_fallback = os.path.join('core', 'yolov8n-pose.pt')
                if not os.path.exists(pose_fallback) and not os.path.exists('yolov8n-pose.pt'):
                    # Ensure it downloads to core if not present
                    self.pose_model = YOLO(pose_fallback)
                else:
                    self.pose_model = YOLO(pose_fallback if os.path.exists(pose_fallback) else 'yolov8n-pose.pt')
                logger.info("✅ Loaded YOLOv8n-Pose")
            
            # Prefer GPU if available, but fall back safely to CPU if any CUDA/NMS issue occurs.
            target_device = 'cpu'
            if torch is not None and torch.cuda.is_available():
                try:
                    self.pose_model.to('cuda')
                    # Optional lightweight sanity check: run a tiny dummy inference
                    dummy = np.zeros((64, 64, 3), dtype=np.uint8)
                    _ = self.pose_model(dummy, conf=0.5, verbose=False, device='cuda')
                    target_device = 'cuda'
                    logger.info("🔧 Pose model set to CUDA inference (RTX GPU detected)")
                except Exception as cuda_error:
                    logger.warning(f"⚠️ Pose model CUDA path failed, falling back to CPU: {cuda_error}")
                    self.pose_model.to('cpu')
                    target_device = 'cpu'
            else:
                self.pose_model.to('cpu')
                target_device = 'cpu'

            logger.info(f"🔧 Pose model device: {target_device}")
                
        except ImportError:
            logger.warning("⚠️ Ultralytics not installed. Install with: pip install ultralytics")
            logger.warning("⚠️ Falling back to anatomical detection without pose")
        except Exception as e:
            logger.error(f"❌ Failed to load pose model: {e}")
            logger.warning("⚠️ Falling back to anatomical detection without pose")
    
    def detect_with_pose(self, frame: np.ndarray, sector: Optional[str] = None, 
                        confidence: float = 0.25,
                        required_ppe: Optional[List[str]] = None) -> Dict:
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
            
            # 1️⃣ Detect poses (persons with keypoints) - use current model device (CPU or CUDA)
            pose_results = self.pose_model(
                frame_for_inference,
                conf=self.pose_confidence_threshold,
                verbose=False
            )
            
            # 2️⃣ Detect PPE items (using existing detector)
            ppe_detections = []
            if self.ppe_detector:
                # Lightweight cadence control: run SH17 every Nth frame, reuse last detections otherwise.
                self._frame_counter += 1
                run_new_sh17 = (
                    self.sh17_every_n <= 1 or
                    self._frame_counter % self.sh17_every_n == 0 or
                    not self._last_ppe_detections
                )

                if run_new_sh17:
                    ppe_result = self.ppe_detector.detect_ppe(frame, sector, confidence)
                    if isinstance(ppe_result, list):
                        ppe_detections = ppe_result
                    elif isinstance(ppe_result, dict):
                        ppe_detections = ppe_result.get('detections', [])
                    else:
                        ppe_detections = []

                    # Cache for intermediate frames
                    self._last_ppe_detections = ppe_detections
                else:
                    # Reuse cached SH17 detections for this frame; pose/keypoints are still fresh.
                    ppe_detections = self._last_ppe_detections
            
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
                enhanced_detections, sector, required_ppe
            )
            
            # 🔍 QUALITY CHECK - If compliance is 0% and we have people, might be detection/association issue
            if compliance_result['people_detected'] > 0 and compliance_result['compliance_rate'] == 0:
                logger.warning(f"⚠️ 0% compliance detected for {compliance_result['people_detected']} people - checking quality")
                # Log high-level stats
                logger.debug(f"PPE detections available: {len(ppe_detections)}")
                logger.debug(f"Persons with pose: {len(persons_with_pose)}")

                # 🧪 Detailed IoU debug for helmet vs head/person bboxes.
                # Amaç: SH17 'helmet' kutularını gerçekten head bölgesiyle neden eşleştiremediğimizi görmek.
                try:
                    helmet_cfg = PPE_CONFIG.get('helmet', {})
                    helmet_classes = [str(c).lower() for c in helmet_cfg.get('model_classes', [])]

                    helmet_items = []
                    for det in ppe_detections:
                        cname = str(det.get('class_name', '')).lower()
                        if any(cls in cname for cls in helmet_classes):
                            helmet_items.append(det)

                    if helmet_items:
                        logger.debug(
                            f"🧪 Helmet IoU debug: {len(helmet_items)} helmet candidates, "
                            f"{len(persons_with_pose)} persons"
                        )
                        for idx, person in enumerate(persons_with_pose):
                            regions = person.get('anatomical_regions', {}) or {}
                            head_region = regions.get('head') or regions.get('full_body') or person.get('bbox')
                            person_bbox = person.get('bbox')

                            logger.debug(
                                f"Person {idx}: head_region={head_region}, person_bbox={person_bbox}"
                            )

                            for h in helmet_items:
                                hb = h.get('bbox', [])
                                if not head_region or not person_bbox or len(hb) != 4:
                                    continue

                                iou_head = self._calculate_iou(hb, head_region)
                                iou_person = self._calculate_iou(hb, person_bbox)
                                logger.debug(
                                    f"  helmet_bbox={hb}, "
                                    f"IoU_head={iou_head:.3f}, IoU_person={iou_person:.3f}"
                                )
                except Exception as debug_err:
                    # Debug amaçlı; ana akışı asla bozmasın.
                    logger.debug(f"Helmet IoU debug failed: {debug_err}")
            
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
            # Handle both single result and list of results
            if not isinstance(pose_results, (list, tuple)):
                pose_results = [pose_results]
            
            for result in pose_results:
                # Check if result has required attributes
                if not hasattr(result, 'keypoints') or result.keypoints is None:
                    logger.debug("⚠️ No keypoints in pose result, skipping")
                    continue
                
                # Safely get bounding boxes and keypoints
                try:
                    if result.boxes is not None and hasattr(result.boxes, 'xyxy'):
                        boxes = result.boxes.xyxy.cpu().numpy() if hasattr(result.boxes.xyxy, 'cpu') else []
                    else:
                        boxes = []
                    
                    if result.keypoints is not None and hasattr(result.keypoints, 'xy'):
                        keypoints = result.keypoints.xy.cpu().numpy() if hasattr(result.keypoints.xy, 'cpu') else []
                    else:
                        keypoints = []
                    
                    if result.keypoints is not None and hasattr(result.keypoints, 'conf'):
                        confidences = result.keypoints.conf.cpu().numpy() if hasattr(result.keypoints.conf, 'cpu') else []
                    else:
                        confidences = []
                    
                    # Get box confidences safely
                    box_confidences = []
                    if result.boxes is not None and hasattr(result.boxes, 'conf'):
                        try:
                            box_confidences = result.boxes.conf.cpu().numpy() if hasattr(result.boxes.conf, 'cpu') else []
                        except Exception:
                            box_confidences = []
                    
                except Exception as attr_error:
                    logger.warning(f"⚠️ Error accessing pose result attributes: {attr_error}")
                    continue

                # Optional ByteTrack-based tracking to obtain stable person IDs
                tracker_ids = None
                if self.byte_tracker is not None and sv is not None:
                    try:
                        detections = sv.Detections.from_ultralytics(result)
                        detections = self.byte_tracker.update_with_detections(detections)
                        tracker_ids = detections.tracker_id

                        # Sanity check: tracker_ids length should match number of boxes
                        if tracker_ids is not None and len(tracker_ids) != len(boxes):
                            logger.debug(
                                "ByteTrack tracker_ids length mismatch with pose boxes; "
                                "ignoring tracker_ids for this frame."
                            )
                            tracker_ids = None
                    except Exception as track_error:
                        logger.warning(f"ByteTrack update failed, disabling tracker: {track_error}")
                        self.byte_tracker = None
                        tracker_ids = None
                
                # Ensure all arrays have same length
                min_len = min(len(boxes), len(keypoints), len(confidences))
                if min_len == 0:
                    logger.debug("⚠️ No valid pose detections found")
                    continue
                
                for i in range(min_len):
                    try:
                        box = boxes[i]
                        kpts = keypoints[i]
                        kpt_conf = confidences[i] if i < len(confidences) else np.array([])
                        
                        x1, y1, x2, y2 = box
                        
                        # 🔧 STRICT BBOX CLIPPING - Ensure person bbox stays within frame
                        frame_height, frame_width = frame_shape[:2]
                        x1 = max(0, min(x1, frame_width - 1))
                        x2 = max(x1 + 1, min(x2, frame_width))
                        y1 = max(0, min(y1, frame_height - 1))
                        y2 = max(y1 + 1, min(y2, frame_height))
                        
                        # Extract keypoints with confidence
                        keypoint_data = []
                        if len(kpts) > 0 and len(kpt_conf) > 0:
                            for j in range(min(len(kpts), len(kpt_conf))):
                                conf = kpt_conf[j] if j < len(kpt_conf) else 0.0
                                if conf > self.keypoint_confidence_threshold:
                                    kpt = kpts[j]
                                    if len(kpt) >= 2:
                                        keypoint_data.append({
                                            'index': j,
                                            'x': float(kpt[0]),
                                            'y': float(kpt[1]),
                                            'confidence': float(conf)
                                        })
                        
                        # Determine stable track ID if available from ByteTrack
                        track_id = None
                        if tracker_ids is not None and i < len(tracker_ids):
                            raw_tid = tracker_ids[i]
                            if raw_tid is not None:
                                try:
                                    track_id = int(raw_tid)
                                except (TypeError, ValueError):
                                    track_id = None

                        # Use track_id for keypoint smoothing when available, otherwise fallback to index
                        smoothing_id = track_id if track_id is not None else i
                        keypoint_data = self._smooth_keypoints(keypoint_data, smoothing_id)
                        
                        # Calculate anatomical regions from keypoints
                        anatomical_regions = self._calculate_anatomical_regions_from_pose(
                            keypoint_data, (x1, y1, x2, y2), frame_shape
                        )
                        
                        # Get box confidence safely
                        box_confidence = 0.9  # default
                        if i < len(box_confidences):
                            box_confidence = float(box_confidences[i])
                        elif result.boxes is not None and hasattr(result.boxes, 'conf'):
                            try:
                                if hasattr(result.boxes.conf, '__getitem__'):
                                    box_confidence = float(result.boxes.conf[i])
                            except (IndexError, TypeError):
                                pass
                        
                        person_dict = {
                            'bbox': [float(x1), float(y1), float(x2), float(y2)],
                            'keypoints': keypoint_data,
                            'anatomical_regions': anatomical_regions,
                            'class_name': 'person',
                            'confidence': box_confidence
                        }
                        if track_id is not None:
                            person_dict['track_id'] = track_id

                        persons.append(person_dict)
                    except Exception as person_error:
                        logger.warning(f"⚠️ Error processing person {i}: {person_error}")
                        continue
            
            logger.debug(f"📊 Extracted {len(persons)} persons with pose data")
            return persons
            
        except Exception as e:
            logger.error(f"❌ Pose extraction failed: {e}")
            import traceback
            logger.debug(f"❌ Pose extraction traceback: {traceback.format_exc()}")
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

        # 🎯 HANDS REGION - Using wrists and elbows (approximate area for gloves)
        hands_region = None
        left_elbow = get_kpt(7)
        right_elbow = get_kpt(8)
        left_wrist = get_kpt(9)
        right_wrist = get_kpt(10)

        hand_points = [p for p in [left_elbow, right_elbow, left_wrist, right_wrist] if p]
        if hand_points:
            hand_xs = [p['x'] for p in hand_points]
            hand_ys = [p['y'] for p in hand_points]

            valid_xs = [x for x in hand_xs if 0 <= x < frame_width]
            valid_ys = [y for y in hand_ys if 0 <= y < frame_height]

            if valid_xs and valid_ys:
                hands_width = max(valid_xs) - min(valid_xs)
                hands_height = max(valid_ys) - min(valid_ys)

                if hands_width < 5:
                    hands_width = (px2 - px1) * 0.3
                if hands_height < 5:
                    hands_height = (py2 - py1) * 0.2

                hands_x1 = min(valid_xs) - hands_width * 0.4
                hands_x2 = max(valid_xs) + hands_width * 0.4
                hands_y1 = min(valid_ys) - hands_height * 0.4
                hands_y2 = max(valid_ys) + hands_height * 0.4

                hands_region = clip_bbox(hands_x1, hands_y1, hands_x2, hands_y2)

        # Fallback: approximate hands region from torso if keypoints missing
        if hands_region is None:
            if torso_region is not None:
                tx1, ty1, tx2, ty2 = torso_region
                t_height = ty2 - ty1
                hands_x1 = tx1
                hands_x2 = tx2
                hands_y1 = ty1 + t_height * 0.3
                hands_y2 = ty2 + t_height * 0.3
                hands_region = clip_bbox(hands_x1, hands_y1, hands_x2, hands_y2)
            else:
                # Use middle-lower part of the person bbox
                person_width = px2 - px1
                person_height = py2 - py1
                hands_width = person_width * 0.6
                person_center_x = (px1 + px2) / 2
                hands_x1 = max(0, person_center_x - hands_width / 2)
                hands_x2 = min(frame_width, person_center_x + hands_width / 2)
                hands_y1 = max(0, py1 + person_height * 0.35)
                hands_y2 = min(frame_height, py1 + person_height * 0.75)
                hands_region = [hands_x1, hands_y1, hands_x2, hands_y2]

        # Full body region can be useful for suits or fallback
        full_body_region = clip_bbox(px1, py1, px2, py2)
        
        return {
            'head': head_region,
            'torso': torso_region,
            'feet': feet_region,
            'hands': hands_region,
            'full_body': full_body_region
        }
    
    def _associate_ppe_with_pose(self, persons: List[Dict], ppe_detections: List[Dict],
                                frame_shape: Tuple) -> List[Dict]:
        """Associate PPE items with persons using pose-based anatomical regions."""

        # Normalize PPE detections by class name (lowercase) and group by canonical PPE type
        ppe_by_type: Dict[str, List[Dict]] = {ptype: [] for ptype in PPE_CONFIG.keys()}

        for det in ppe_detections:
            class_name = str(det.get('class_name', '')).lower()
            if class_name.startswith('no-'):
                # Sistem tarafından üretilen negatif kutuları dikkate alma
                continue
            for ppe_type, cfg in PPE_CONFIG.items():
                if any(cls in class_name for cls in cfg['model_classes']):
                    ppe_by_type[ppe_type].append(det)
                    break

        logger.debug(
            "🔍 PPE separation (by type): " +
            ", ".join(f"{ptype}={len(items)}" for ptype, items in ppe_by_type.items())
        )

        enhanced_persons: List[Dict] = []

        for person in persons:
            regions = person['anatomical_regions']
            person_bbox = person['bbox']

            person_ppe: Dict[str, Optional[Dict]] = {}
            compliance: Dict[str, bool] = {}

            for ppe_type, cfg in PPE_CONFIG.items():
                region_name = cfg['region']
                region_bbox = regions.get(region_name)
                if region_bbox is None:
                    # Fallback: full body bölgesini kullan
                    region_bbox = regions.get('full_body', person_bbox)

                best_match = self._find_best_ppe_match(
                    ppe_by_type.get(ppe_type, []),
                    region_bbox,
                    person_bbox,
                    ppe_type=ppe_type
                )

                person_ppe[ppe_type] = best_match
                compliance[ppe_type] = best_match is not None

            enhanced_persons.append(
                {
                    'person': person,
                    'ppe': person_ppe,
                    'regions': regions,
                    'compliance': compliance,
                }
            )

        return enhanced_persons
    
    def _find_best_ppe_match(self, ppe_items: List[Dict], region: List[float], 
                            person_bbox: List[float], ppe_type: str = 'general') -> Optional[Dict]:
        """Find best PPE match for anatomical region using IoU with type-specific thresholds."""
        best_match = None
        best_iou = 0.0
        best_person_iou = 0.0
        best_center_y: Optional[float] = None
        
        # Type-specific thresholds (shoes need lower threshold due to occlusion)
        iou_threshold = {
            'helmet': 0.03,        # slightly more tolerant for helmets
            'safety_vest': 0.05,
            'safety_shoes': 0.02,  # Lower for shoes - often partially visible
            'gloves': 0.05,
            'safety_glasses': 0.05,
            'face_mask': 0.05,
            'safety_suit': 0.05,
            'general': 0.05
        }.get(ppe_type, 0.05)
        
        person_iou_threshold = {
            'helmet': 0.08,        # allow slightly weaker overlap with person
            'safety_vest': 0.1,
            'safety_shoes': 0.05,  # Lower for shoes
            'gloves': 0.1,
            'safety_glasses': 0.1,
            'face_mask': 0.1,
            'safety_suit': 0.1,
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
                best_person_iou = person_iou
                best_match = ppe
                try:
                    _, py1, _, py2 = person_bbox
                    _, y1, _, y2 = ppe_bbox
                    best_center_y = (float(y1) + float(y2)) / 2.0
                except Exception:
                    best_center_y = None
        
        # Standart kural: bölge IoU eşiğinin üzerinde ise kabul et
        if best_match is not None and best_iou > iou_threshold:
            return best_match
        
        # Ek güvenli fallback: Özellikle kask için, baş bölgesine IoU düşük olsa bile
        # kask kutusu kişinin üst kısmında ve kişi ile makul IoU'ya sahipse kabul et.
        if ppe_type == 'helmet' and best_match is not None and best_person_iou > 0:
            try:
                px1, py1, px2, py2 = person_bbox
                person_height = max(float(py2) - float(py1), 1.0)
                top_fraction = py1 + person_height * 0.45  # üst ~%45'lik dilim "baş" kabul
                
                if best_center_y is not None and best_person_iou >= 0.20 and best_center_y <= top_fraction:
                    logger.debug(
                        f"✅ Helmet fallback match accepted: best_iou={best_iou:.3f}, "
                        f"person_iou={best_person_iou:.3f}, center_y={best_center_y:.1f}, "
                        f"person_top_limit={top_fraction:.1f}"
                    )
                    return best_match
            except Exception:
                # Fallback teşhis amaçlı; hata durumunda sadece normal kurala geri döneriz.
                pass
        
        return None
    
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
                                        sector: Optional[str],
                                        required_ppe: Optional[List[str]] = None) -> Dict:
        """Calculate compliance with pose-aware scoring"""
        
        total_people = len(enhanced_persons)
        compliant_people = 0
        violations = []
        all_detections = []
        
        # Pose-aware sistemin desteklediği PPE türleri (kanonik isimler)
        supported_types = set(PPE_CONFIG.keys())
        supported_required: Optional[List[str]] = None
        
        if required_ppe is not None:
            # İsimleri normalize et (case-insensitive, trim)
            normalized_required = []
            for item in required_ppe:
                if item is None:
                    continue
                try:
                    normalized_required.append(str(item).strip().lower())
                except Exception:
                    continue
            # Sadece pose-aware'in gerçekten takip edebildiği PPE türlerini dikkate al
            supported_required = [item for item in normalized_required if item in supported_types]
            # Desteklenmeyen PPE türleri SH17/hybrid tarafında ele alınır;
            # burada sadece log ile bilgilendiriyoruz, uyum hesabına dahil etmiyoruz.
            unsupported = [item for item in normalized_required if item not in supported_types]
            if unsupported:
                logger.debug(f"⚠️ Pose-aware compliance, şu PPE türlerini desteklemiyor ve yoksayıyor: {unsupported}")

        # Violation üretimi için: PPE sadece zorunluysa "eksik" sayılır.
        # required_ppe None ise: sadece default_critical=True olan PPE'ler ihlal üretir.
        def is_required_for_violation(ppe_type: str) -> bool:
            cfg = PPE_CONFIG.get(ppe_type, {})
            if required_ppe is None:
                return bool(cfg.get('default_critical', False))
            if supported_required is None:
                return False
            return ppe_type in supported_required
        
        for person_data in enhanced_persons:
            person = person_data['person']
            ppe = person_data['ppe']
            regions = person_data['regions']
            compliance = person_data['compliance']
            
            # Add person detection
            all_detections.append(person)
            
            # Add PPE detections with anatomical regions (positive + negative)
            for ppe_type, cfg in PPE_CONFIG.items():
                region_name = cfg['region']
                region_bbox = regions.get(region_name) or regions.get('full_body')
                if region_bbox is None:
                    continue

                item = ppe.get(ppe_type)
                if item:
                    all_detections.append(
                        {
                            'bbox': region_bbox,
                            'class_name': cfg['pos_label'],
                            'confidence': float(item.get('confidence', 0.9)),
                            'missing': False,
                            'pose_based': True,
                        }
                    )
                else:
                    if is_required_for_violation(ppe_type):
                        violations.append(cfg['violation_tr'])
                        all_detections.append(
                            {
                                'bbox': region_bbox,
                                'class_name': cfg['neg_label'],
                                'confidence': 0.9,
                                'missing': True,
                                'pose_based': True,
                            }
                        )
            
            # Instantaneous compliance for this frame/person
            if required_ppe is not None:
                if not supported_required:
                    # Konfig sadece desteklenmeyen PPE'ler içeriyorsa, pose-aware açısından herkes uyumlu sayılır.
                    is_compliant = True
                else:
                    is_compliant = True
                    for ppe_type in supported_required:
                        if not compliance.get(ppe_type, False):
                            is_compliant = False
                            break
            else:
                # Geriye uyumlu davranış: default_critical=True olan PPE'ler gereklidir (kask+yelek+ayakkabı).
                critical_types = [t for t, cfg in PPE_CONFIG.items() if cfg.get('default_critical', False)]
                is_compliant = all(compliance.get(t, False) for t in critical_types)

            # Temporal voting using track_id when available
            temporal_compliant = is_compliant
            track_id = person.get('track_id') if isinstance(person, dict) else None

            if track_id is not None:
                try:
                    tid = int(track_id)
                except (TypeError, ValueError):
                    tid = None

                if tid is not None:
                    history = self.compliance_history.get(tid)
                    if history is None:
                        history = deque(maxlen=self.temporal_window_size)
                        self.compliance_history[tid] = history

                    history.append(bool(is_compliant))

                    if len(history) >= self.temporal_required_positive:
                        positive_count = sum(1 for v in history if v)
                        # Orantısal eşik: pencere dolduğunda required/window_size oranı uygulanır.
                        # Örn: 10/15 → %66 frame'de uyumluysa compliant say.
                        proportional_threshold = max(
                            1,
                            round(self.temporal_required_positive * len(history) / self.temporal_window_size)
                        )
                        temporal_compliant = positive_count >= proportional_threshold

            if temporal_compliant:
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
