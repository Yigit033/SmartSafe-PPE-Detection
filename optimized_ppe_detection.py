#!/usr/bin/env python3
"""
Optimized PPE Detection System
High-performance real-time PPE detection with SH17 model
"""

import cv2
import numpy as np
import time
import torch
from ultralytics import YOLO
import logging
from collections import deque
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SH17 Dataset class names
SH17_CLASSES = {
    0: 'person', 1: 'head', 2: 'face', 3: 'glasses',
    4: 'face_mask_medical', 5: 'face_guard', 6: 'ear', 7: 'earmuffs',
    8: 'hands', 9: 'gloves', 10: 'foot', 11: 'shoes',
    12: 'safety_vest', 13: 'tools', 14: 'helmet',
    15: 'medical_suit', 16: 'safety_suit'
}

class OptimizedPPEDetector:
    def __init__(self):
        self.model = None
        self.fps_queue = deque(maxlen=30)
        self.frame_skip = 2  # Process every 2nd frame
        self.frame_count = 0
        
        # PPE colors
        self.colors = {
            'person': (255, 255, 255),
            'helmet': (0, 255, 0),        # Green - Critical
            'safety_vest': (0, 255, 0),   # Green - Critical
            'safety_suit': (0, 255, 255), # Cyan - Critical
            'violation': (0, 0, 255),     # Red
            'compliant': (0, 255, 0)      # Green
        }
        
    def load_model(self, use_optimized=True):
        """Load optimized model"""
        try:
            if use_optimized:
                # Try YOLOv8n first for speed
                model_path = "yolov8n.pt"
                model_type = "YOLOv8n (Fast)"
            else:
                # Use SH17 model if accuracy needed
                model_path = "data/models/yolo9e.pt"
                model_type = "YOLOv9-e (SH17)"
            
            self.model = YOLO(model_path)
            self.model.to('cpu')
            
            # Optimize model settings
            self.model.model.eval()  # Set to evaluation mode
            if hasattr(self.model.model, 'fuse'):
                self.model.model.fuse()  # Fuse conv and bn layers
            
            logger.info(f"✅ {model_type} model loaded")
            return True
            
        except Exception as e:
            logger.error(f"❌ Model load failed: {e}")
            return False
    
    def setup_camera(self, resolution=(640, 480)):
        """Setup optimized camera"""
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("❌ Camera not found!")
            return None
        
        # Optimize camera settings
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce lag
        
        # Try MJPG codec for better performance
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        
        logger.info(f"✅ Camera setup: {resolution[0]}x{resolution[1]}")
        return cap
    
    def detect_optimized(self, frame):
        """Optimized detection with frame skipping"""
        self.frame_count += 1
        
        # Skip frames for better performance
        if self.frame_count % self.frame_skip != 0:
            return []
        
        try:
            # Resize frame for faster inference
            original_shape = frame.shape[:2]
            frame_resized = cv2.resize(frame, (320, 320))  # Smaller input
            
            # Run detection
            results = self.model(frame_resized, conf=0.4, verbose=False)
            
            detections = []
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        # Scale back to original size
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        x1 = int(x1 * frame.shape[1] / 320)
                        y1 = int(y1 * frame.shape[0] / 320)
                        x2 = int(x2 * frame.shape[1] / 320)
                        y2 = int(y2 * frame.shape[0] / 320)
                        
                        confidence = box.conf[0].cpu().numpy()
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        # Use COCO classes for YOLOv8n, SH17 for YOLOv9-e
                        if hasattr(self.model, 'names'):
                            class_name = self.model.names[class_id]
                        else:
                            class_name = SH17_CLASSES.get(class_id, f"class_{class_id}")
                        
                        detections.append({
                            'bbox': (x1, y1, x2, y2),
                            'confidence': float(confidence),
                            'class_name': class_name
                        })
            
            return detections
            
        except Exception as e:
            logger.error(f"Detection error: {e}")
            return []
    
    def analyze_ppe_compliance(self, detections, required_ppe=None):
        """Analyze PPE compliance based on company requirements"""
        if required_ppe is None:
            required_ppe = ['helmet', 'vest']  # Default requirements
        
        people = [d for d in detections if d['class_name'] == 'person']
        ppe_items = [d for d in detections if d['class_name'] in 
                    ['helmet', 'safety_vest', 'safety_suit', 'hard hat', 'glasses', 'gloves', 'shoes', 'mask']]
        
        compliance_status = []
        
        for person in people:
            # Simple proximity-based PPE association
            person_bbox = person['bbox']
            detected_ppe = {
                'helmet': False,
                'vest': False,
                'glasses': False,
                'gloves': False,
                'shoes': False,
                'mask': False
            }
            
            for ppe in ppe_items:
                if self.boxes_overlap(person_bbox, ppe['bbox']):
                    if 'helmet' in ppe['class_name'] or 'hard hat' in ppe['class_name']:
                        detected_ppe['helmet'] = True
                    elif 'vest' in ppe['class_name'] or 'suit' in ppe['class_name']:
                        detected_ppe['vest'] = True
                    elif 'glasses' in ppe['class_name']:
                        detected_ppe['glasses'] = True
                    elif 'gloves' in ppe['class_name']:
                        detected_ppe['gloves'] = True
                    elif 'shoes' in ppe['class_name']:
                        detected_ppe['shoes'] = True
                    elif 'mask' in ppe['class_name']:
                        detected_ppe['mask'] = True
            
            # Check compliance based on required PPE
            missing_ppe = []
            for ppe_type in required_ppe:
                if not detected_ppe.get(ppe_type, False):
                    missing_ppe.append(ppe_type)
            
            is_compliant = len(missing_ppe) == 0
            
            compliance_status.append({
                'person': person,
                'detected_ppe': detected_ppe,
                'missing_ppe': missing_ppe,
                'compliant': is_compliant
            })
        
        return compliance_status
    
    def boxes_overlap(self, box1, box2, threshold=0.1):
        """Check if two boxes overlap"""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Calculate intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i <= x1_i or y2_i <= y1_i:
            return False
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        iou = intersection / union if union > 0 else 0
        return iou > threshold
    
    def draw_results(self, frame, detections, compliance_status):
        """Draw optimized results"""
        # Draw detections
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            class_name = det['class_name']
            confidence = det['confidence']
            
            # Color based on class
            from utils.visual_overlay import draw_styled_box, get_class_color
            
            color = get_class_color(class_name, is_missing=False)
            if class_name in ['helmet', 'safety_vest', 'safety_suit']:
                color = (0, 255, 0)  # Yeşil - Uyumlu
            
            # Draw label
            label = f"{class_name} {confidence:.2f}"
            
            # Profesyonel bounding box çiz
            frame = draw_styled_box(frame, x1, y1, x2, y2, label, color)
        
        # Draw compliance status
        y_offset = 30
        for status in compliance_status:
            person_id = f"Person"
            ppe_text = f"Helmet: {'✓' if status['has_helmet'] else '✗'} | "
            ppe_text += f"Vest: {'✓' if status['has_vest'] else '✗'}"
            
            color = self.colors['compliant'] if status['compliant'] else self.colors['violation']
            
            cv2.putText(frame, f"{person_id}: {ppe_text}", (10, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            y_offset += 25
        
        return frame
    
    def run_detection(self, resolution=(640, 480), use_optimized=True):
        """Run optimized real-time detection"""
        logger.info("🚀 Starting Optimized PPE Detection...")
        
        # Load model
        if not self.load_model(use_optimized):
            return
        
        # Setup camera
        cap = self.setup_camera(resolution)
        if cap is None:
            return
        
        logger.info("🎥 Press 'q' to quit, 'f' to toggle model, 's' to screenshot")
        
        while True:
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                logger.error("❌ Failed to read frame")
                break
            
            # Run optimized detection
            detections = self.detect_optimized(frame)
            
            # Analyze PPE compliance
            compliance_status = self.analyze_ppe_compliance(detections)
            
            # Draw results
            frame = self.draw_results(frame, detections, compliance_status)
            
            # Calculate FPS
            frame_time = time.time() - start_time
            self.fps_queue.append(frame_time)
            
            if self.fps_queue:
                current_fps = 1.0 / (sum(self.fps_queue) / len(self.fps_queue))
                
                # Draw performance info
                cv2.putText(frame, f"FPS: {current_fps:.1f}", 
                           (frame.shape[1] - 150, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                cv2.putText(frame, f"Detections: {len(detections)}", 
                           (frame.shape[1] - 150, 70), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            
            # Show frame
            cv2.imshow('Optimized PPE Detection', frame)
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('f'):
                # Toggle between models
                use_optimized = not use_optimized
                logger.info(f"Switching to {'Optimized' if use_optimized else 'SH17'} model...")
                self.load_model(use_optimized)
            elif key == ord('s'):
                # Save screenshot
                cv2.imwrite(f"ppe_screenshot_{int(time.time())}.jpg", frame)
                logger.info("Screenshot saved!")
        
        cap.release()
        cv2.destroyAllWindows()
        logger.info("✅ Detection completed")

def main():
    """Main function"""
    detector = OptimizedPPEDetector()
    
    # Test with different settings
    print("🎯 Choose detection mode:")
    print("1. Fast Mode (YOLOv8n + 640x480)")
    print("2. Accurate Mode (SH17 YOLOv9-e + 320x320)")
    print("3. Balanced Mode (YOLOv8n + 320x320)")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        detector.run_detection(resolution=(640, 480), use_optimized=True)
    elif choice == "2":
        detector.run_detection(resolution=(320, 320), use_optimized=False)
    elif choice == "3":
        detector.run_detection(resolution=(320, 320), use_optimized=True)
    else:
        logger.info("Using default fast mode...")
        detector.run_detection(resolution=(640, 480), use_optimized=True)

if __name__ == "__main__":
    main() 