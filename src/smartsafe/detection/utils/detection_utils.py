"""
Detection utilities for PPE Detection System
Modern computer vision helper functions
"""

import cv2
import numpy as np
import torch
from typing import List, Tuple, Dict, Optional
import logging
from pathlib import Path
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DetectionUtils:
    """Utility functions for object detection"""
    
    @staticmethod
    def non_max_suppression(boxes: np.ndarray, 
                           scores: np.ndarray, 
                           score_threshold: float = 0.5,
                           iou_threshold: float = 0.4) -> List[int]:
        """
        Apply Non-Maximum Suppression to eliminate redundant detections
        
        Args:
            boxes: Array of bounding boxes [x1, y1, x2, y2]
            scores: Array of confidence scores
            score_threshold: Minimum score threshold
            iou_threshold: IoU threshold for suppression
            
        Returns:
            List of indices of boxes to keep
        """
        if len(boxes) == 0:
            return []
        
        # Filter by score threshold
        valid_indices = scores > score_threshold
        boxes = boxes[valid_indices]
        scores = scores[valid_indices]
        
        if len(boxes) == 0:
            return []
        
        # Calculate areas
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        
        # Sort by scores
        order = scores.argsort()[::-1]
        
        keep = []
        while len(order) > 0:
            # Pick the detection with highest score
            i = order[0]
            keep.append(i)
            
            if len(order) == 1:
                break
            
            # Calculate IoU with remaining detections
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            
            w = np.maximum(0, xx2 - xx1)
            h = np.maximum(0, yy2 - yy1)
            intersection = w * h
            
            iou = intersection / (areas[i] + areas[order[1:]] - intersection)
            
            # Keep detections with IoU less than threshold
            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]
        
        return keep
    
    @staticmethod
    def calculate_iou(box1: Tuple[int, int, int, int], 
                     box2: Tuple[int, int, int, int]) -> float:
        """
        Calculate Intersection over Union (IoU) between two bounding boxes
        
        Args:
            box1: First bounding box (x1, y1, x2, y2)
            box2: Second bounding box (x1, y1, x2, y2)
            
        Returns:
            IoU value between 0 and 1
        """
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection coordinates
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        # Check if there's no intersection
        if x2_i <= x1_i or y2_i <= y1_i:
            return 0.0
        
        # Calculate intersection area
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        
        # Calculate union area
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    @staticmethod
    def resize_with_padding(image: np.ndarray, 
                           target_size: Tuple[int, int],
                           fill_value: int = 114) -> Tuple[np.ndarray, float, Tuple[int, int]]:
        """
        Resize image while maintaining aspect ratio with padding
        
        Args:
            image: Input image
            target_size: Target size (width, height)
            fill_value: Padding fill value
            
        Returns:
            Resized image, scale factor, padding (pad_w, pad_h)
        """
        h, w = image.shape[:2]
        target_w, target_h = target_size
        
        # Calculate scale factor
        scale = min(target_w / w, target_h / h)
        
        # Calculate new size
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # Resize image
        if scale != 1:
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # Calculate padding
        pad_w = (target_w - new_w) // 2
        pad_h = (target_h - new_h) // 2
        
        # Add padding
        top = pad_h
        bottom = target_h - new_h - pad_h
        left = pad_w
        right = target_w - new_w - pad_w
        
        image = cv2.copyMakeBorder(image, top, bottom, left, right, 
                                  cv2.BORDER_CONSTANT, value=[fill_value] * 3)
        
        return image, scale, (pad_w, pad_h)
    
    @staticmethod
    def rescale_boxes(boxes: np.ndarray, 
                     scale: float, 
                     padding: Tuple[int, int]) -> np.ndarray:
        """
        Rescale bounding boxes back to original image coordinates
        
        Args:
            boxes: Bounding boxes in resized image coordinates
            scale: Scale factor used for resizing
            padding: Padding (pad_w, pad_h) added during resizing
            
        Returns:
            Bounding boxes in original image coordinates
        """
        pad_w, pad_h = padding
        
        # Remove padding
        boxes[:, [0, 2]] -= pad_w
        boxes[:, [1, 3]] -= pad_h
        
        # Rescale
        boxes /= scale
        
        # Ensure boxes are within bounds
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, None)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, None)
        
        return boxes
    
    @staticmethod
    def draw_detection_box(image: np.ndarray,
                          box: Tuple[int, int, int, int],
                          label: str,
                          confidence: float,
                          color: Tuple[int, int, int] = (0, 255, 0),
                          thickness: int = 2) -> np.ndarray:
        """
        Draw detection bounding box with label
        
        Args:
            image: Input image
            box: Bounding box (x1, y1, x2, y2)
            label: Class label
            confidence: Detection confidence
            color: Box color (B, G, R)
            thickness: Line thickness
            
        Returns:
            Image with drawn bounding box
        """
        x1, y1, x2, y2 = [int(coord) for coord in box]
        
        # Prepare label text
        label_text = f"{label} {confidence:.2f}"
        
        # Profesyonel bounding box çiz
        from utils.visual_overlay import draw_styled_box
        image = draw_styled_box(image, x1, y1, x2, y2, label_text, color, thickness)
        
        return image
    
    @staticmethod
    def create_detection_overlay(image: np.ndarray,
                               detections: List[Dict],
                               class_colors: Optional[Dict[str, Tuple[int, int, int]]] = None) -> np.ndarray:
        """
        Create detection overlay on image
        
        Args:
            image: Input image
            detections: List of detection dictionaries
            class_colors: Color mapping for classes
            
        Returns:
            Image with detection overlay
        """
        if class_colors is None:
            class_colors = {
                'person': (255, 255, 255),
                'hard_hat': (0, 255, 0),
                'safety_vest': (0, 255, 255),
                'mask': (255, 0, 255),
                'no_hard_hat': (0, 0, 255),
                'no_safety_vest': (0, 0, 255),
                'no_mask': (0, 0, 255)
            }
        
        overlay = image.copy()
        
        for detection in detections:
            box = detection.get('bbox', [0, 0, 0, 0])
            label = detection.get('class_name', 'unknown')
            confidence = detection.get('confidence', 0.0)
            color = class_colors.get(label, (128, 128, 128))
            
            overlay = DetectionUtils.draw_detection_box(
                overlay, box, label, confidence, color
            )
        
        return overlay
    
    @staticmethod
    def filter_detections_by_area(detections: List[Dict],
                                 min_area: int = 100,
                                 max_area: Optional[int] = None) -> List[Dict]:
        """
        Filter detections by bounding box area
        
        Args:
            detections: List of detection dictionaries
            min_area: Minimum bounding box area
            max_area: Maximum bounding box area (None for no limit)
            
        Returns:
            Filtered detections
        """
        filtered = []
        
        for detection in detections:
            box = detection.get('bbox', [0, 0, 0, 0])
            x1, y1, x2, y2 = box
            area = (x2 - x1) * (y2 - y1)
            
            if area >= min_area:
                if max_area is None or area <= max_area:
                    filtered.append(detection)
        
        return filtered
    
    @staticmethod
    def calculate_detection_metrics(ground_truth: List[Dict],
                                  predictions: List[Dict],
                                  iou_threshold: float = 0.5) -> Dict[str, float]:
        """
        Calculate detection metrics (Precision, Recall, F1)
        
        Args:
            ground_truth: List of ground truth detections
            predictions: List of predicted detections
            iou_threshold: IoU threshold for matching
            
        Returns:
            Dictionary with metrics
        """
        if not ground_truth and not predictions:
            return {'precision': 1.0, 'recall': 1.0, 'f1': 1.0}
        
        if not ground_truth:
            return {'precision': 0.0, 'recall': 1.0, 'f1': 0.0}
        
        if not predictions:
            return {'precision': 1.0, 'recall': 0.0, 'f1': 0.0}
        
        # Match predictions to ground truth
        matched_predictions = set()
        matched_gt = set()
        
        for i, pred in enumerate(predictions):
            pred_box = pred.get('bbox', [0, 0, 0, 0])
            pred_class = pred.get('class_name', '')
            
            best_iou = 0
            best_gt_idx = -1
            
            for j, gt in enumerate(ground_truth):
                if j in matched_gt:
                    continue
                
                gt_box = gt.get('bbox', [0, 0, 0, 0])
                gt_class = gt.get('class_name', '')
                
                if pred_class == gt_class:
                    iou = DetectionUtils.calculate_iou(pred_box, gt_box)
                    if iou > best_iou:
                        best_iou = iou
                        best_gt_idx = j
            
            if best_iou >= iou_threshold:
                matched_predictions.add(i)
                matched_gt.add(best_gt_idx)
        
        # Calculate metrics
        true_positives = len(matched_predictions)
        false_positives = len(predictions) - true_positives
        false_negatives = len(ground_truth) - len(matched_gt)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'true_positives': true_positives,
            'false_positives': false_positives,
            'false_negatives': false_negatives
        }

class ImageProcessor:
    """Image processing utilities for PPE detection"""
    
    @staticmethod
    def enhance_image(image: np.ndarray) -> np.ndarray:
        """
        Enhance image for better detection
        
        Args:
            image: Input image
            
        Returns:
            Enhanced image
        """
        # Convert to LAB color space
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        
        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        
        # Convert back to BGR
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        return enhanced
    
    @staticmethod
    def apply_gaussian_blur(image: np.ndarray, kernel_size: int = 5) -> np.ndarray:
        """
        Apply Gaussian blur for noise reduction
        
        Args:
            image: Input image
            kernel_size: Blur kernel size
            
        Returns:
            Blurred image
        """
        return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0)
    
    @staticmethod
    def adjust_brightness_contrast(image: np.ndarray, 
                                 brightness: int = 0, 
                                 contrast: float = 1.0) -> np.ndarray:
        """
        Adjust image brightness and contrast
        
        Args:
            image: Input image
            brightness: Brightness adjustment (-100 to 100)
            contrast: Contrast adjustment (0.5 to 3.0)
            
        Returns:
            Adjusted image
        """
        adjusted = cv2.convertScaleAbs(image, alpha=contrast, beta=brightness)
        return adjusted

# Usage example
if __name__ == "__main__":
    # Test detection utilities
    print("Testing Detection Utilities...")
    
    # Test IoU calculation
    box1 = (10, 10, 50, 50)
    box2 = (30, 30, 70, 70)
    iou = DetectionUtils.calculate_iou(box1, box2)
    print(f"IoU between {box1} and {box2}: {iou:.3f}")
    
    # Test NMS
    boxes = np.array([[10, 10, 50, 50], [15, 15, 55, 55], [100, 100, 150, 150]])
    scores = np.array([0.9, 0.8, 0.7])
    keep_indices = DetectionUtils.non_max_suppression(boxes, scores)
    print(f"NMS keep indices: {keep_indices}")
    
    print("Detection utilities test completed!") 




"""🧠 NET AÇIKLAMALAR

1. 🎯 NMS (Non-Maximum Suppression)
Ne yapar: Overlapping detection box'ları temizler
Nasıl: En yüksek confidence'a sahip box'u tutar, diğerlerini siler
Neden önemli: Tek obje için 10 tane box çıkmasını engeller

2. 📐 IoU (Intersection over Union)
Ne yapar: İki box'ın ne kadar örtüştüğünü ölçer
Formül: IoU = Intersection Area / Union Area
Değer aralığı: 0.0 (hiç örtüşmüyor) → 1.0 (tamamen örtüşüyor)

3. 🖼️ Image Preprocessing
Ne yapar: Resmi YOLO'ya uygun formata getirir
İşlemler: Resize (640x640), padding ekle, normalize et
Neden önemli: Model training sırasında kullanılan format ile aynı olmalı

4. 📊 Model Evaluation Metrics
Precision: Doğru tahminlerin, tüm positive tahminlere oranı
Recall: Doğru bulunan objelerin, gerçekte var olan objelere oranı
mAP50: Mean Average Precision @IoU=0.5 threshold
mAP50-95: mAP across IoU thresholds 0.5 to 0.95

5. 🧠 YOLO CNN Architecture
Layers: Convolution → Pooling → Feature Maps → Detection Heads
Grid System: Resmi grid'lere böler, her grid'de detection yapar
Multi-Scale: Farklı boyutlardaki objeleri detect eder


❓ SORULARIN NET CEVAPLARI
🎯 IoU ile ilgili:
1. İki box %100 overlap ederse IoU kaç olur?
→ IoU = 1.0 (Perfect match!)

2. Hiç overlap etmezse IoU kaç olur?
→ IoU = 0.0 (No intersection!)

3. IoU = 0.5 ne anlama gelir?
→ %50 örtüşme (İyi detection threshold'u)

🎯 NMS ile ilgili:
4. NMS olmadan ne olur?
→ Aynı obje için 10+ box çıkar (Messy results!)

5. IoU threshold 0.1 vs 0.9 farkı nedir?
→ 0.1: Az örtüşen box'ları bile siler (Aggressive)
→ 0.9: Sadece çok örtüşenleri siler (Conservative)

6. Confidence threshold ile NMS farkı nedir?
→ Confidence: "Bu detection ne kadar güvenilir?" (0.5 = %50 emin)
→ NMS IoU: "Bu box'lar ne kadar örtüşüyor?" (Duplicate removal)"""