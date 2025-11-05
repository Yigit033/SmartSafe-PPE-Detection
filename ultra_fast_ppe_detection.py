# -*- coding: utf-8 -*-
"""
Ultra-Fast PPE Detection System
Target: 30+ FPS real-time detection
Extreme optimization enabled
"""

import cv2
import numpy as np
import time
import torch
from ultralytics import YOLO
import threading
import queue
import logging
from collections import deque
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UltraFastPPEDetector:
    def __init__(self):
        self.model = None
        self.frame_queue = queue.Queue(maxsize=1)
        self.result_queue = queue.Queue(maxsize=1)
        self.fps_history = deque(maxlen=5)
        self.running = False
        
        # Extreme optimization settings
        self.frame_skip = 12  # Process every 12th frame
        self.input_size = 80  # Ultra-tiny input
        self.confidence = 0.8  # Very high confidence
        
        # Performance tracking
        self.frame_count = 0
        self.detection_count = 0
        self.last_detection_time = 0
        
        # Threading
        self.detection_thread = None
        
    def load_ultra_fast_model(self):
        """Load the fastest possible model"""
        try:
            model_path = "yolov8n.pt"
            logger.info(f"Loading ultra-fast model: {model_path}")
            
            self.model = YOLO(model_path)
            self.model.to('cpu')  # Force CPU mode
            
            # Model optimization
            self.model.model.eval()
            if hasattr(self.model.model, 'fuse'):
                self.model.model.fuse()
                
            logger.info("✅ Ultra-fast model loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Model loading failed: {e}")
            return False
    
    def setup_ultra_fast_camera(self):
        """Setup camera with extreme optimization"""
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("❌ Camera not available")
                return None
            
            # Ultra-fast camera settings
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 160)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 120)
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            
            logger.info("✅ Ultra-fast camera setup complete")
            return cap
            
        except Exception as e:
            logger.error(f"❌ Camera setup failed: {e}")
            return None
    
    def ultra_fast_detection_worker(self):
        """Background detection thread"""
        while self.running:
            try:
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get_nowait()
                    
                    # Ultra-fast detection
                    start_time = time.time()
                    
                    # Resize to ultra-tiny input
                    small_frame = cv2.resize(frame, (self.input_size, self.input_size))
                    
                    # Run detection
                    results = self.model.predict(
                        small_frame,
                        conf=self.confidence,
                        iou=0.7,
                        verbose=False,
                        device='cpu'
                    )
                    
                    inference_time = time.time() - start_time
                    
                    # Process results
                    detections = self.process_results_fast(results, frame.shape)
                    
                    # Store results
                    try:
                        self.result_queue.put_nowait((detections, inference_time))
                    except queue.Full:
                        pass
                    
                    self.detection_count += 1
                    self.last_detection_time = inference_time
                    
                else:
                    time.sleep(0.001)
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Detection worker error: {e}")
                continue
    
    def process_results_fast(self, results, original_shape):
        """Ultra-fast result processing"""
        detections = []
        
        for result in results:
            if result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy()
                
                for i in range(len(boxes)):
                    # Scale coordinates
                    x1, y1, x2, y2 = boxes[i]
                    x1 = int(x1 * original_shape[1] / self.input_size)
                    y1 = int(y1 * original_shape[0] / self.input_size)
                    x2 = int(x2 * original_shape[1] / self.input_size)
                    y2 = int(y2 * original_shape[0] / self.input_size)
                    
                    class_id = int(class_ids[i])
                    class_name = self.model.names[class_id]
                    confidence = float(confidences[i])
                    
                    detections.append({
                        'bbox': (x1, y1, x2, y2),
                        'confidence': confidence,
                        'class_name': class_name
                    })
        
        return detections
    
    def analyze_ppe_ultra_fast(self, detections):
        """Ultra-fast PPE analysis"""
        people_count = sum(1 for d in detections if d['class_name'] == 'person')
        
        if people_count == 0:
            return "No people detected"
        
        # Quick PPE check
        has_helmet = any('helmet' in d['class_name'].lower() for d in detections)
        has_vest = any('vest' in d['class_name'].lower() for d in detections)
        
        if has_helmet or has_vest:
            return f"PPE OK ({people_count} people)"
        else:
            return f"PPE MISSING ({people_count} people)"
    
    def draw_ultra_fast_overlay(self, frame, detections, ppe_status, fps):
        """Ultra-fast overlay drawing"""
        h, w = frame.shape[:2]
        
        # FPS display (top-right)
        cv2.putText(frame, f"FPS: {fps:.0f}", (w-100, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # PPE status (top-left)
        color = (0, 255, 0) if "OK" in ppe_status else (0, 0, 255)
        cv2.putText(frame, ppe_status, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Draw detection boxes
        from utils.visual_overlay import draw_styled_box
        
        for det in detections:
            if det['class_name'] == 'person':
                x1, y1, x2, y2 = det['bbox']
                label = "PERSON"
                color = (255, 255, 255)  # Beyaz
                # Profesyonel bounding box çiz
                frame = draw_styled_box(frame, x1, y1, x2, y2, label, color, thickness=1)
        
        return frame
    
    def run_ultra_fast_detection(self):
        """Main ultra-fast detection loop"""
        logger.info("🚀 Starting Ultra-Fast PPE Detection")
        logger.info("🎯 Target: 30+ FPS")
        logger.info("⚡ Extreme optimizations enabled")
        
        # Load model
        if not self.load_ultra_fast_model():
            return False
        
        # Setup camera
        cap = self.setup_ultra_fast_camera()
        if cap is None:
            return False
        
        # Start detection thread
        self.running = True
        self.detection_thread = threading.Thread(target=self.ultra_fast_detection_worker)
        self.detection_thread.daemon = True
        self.detection_thread.start()
        
        logger.info("📺 Press 'q' to quit, 'r' to reset stats")
        
        # Main display loop
        last_detection_result = ([], 0)
        fps_start_time = time.time()
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    logger.warning("Failed to read frame")
                    break
                
                # Frame skipping for extreme speed
                if self.frame_count % self.frame_skip == 0:
                    try:
                        self.frame_queue.put_nowait(frame.copy())
                    except queue.Full:
                        pass
                
                # Get latest detection results
                try:
                    last_detection_result = self.result_queue.get_nowait()
                except queue.Empty:
                    pass
                
                detections, inference_time = last_detection_result
                
                # Calculate FPS
                current_time = time.time()
                if len(self.fps_history) > 0:
                    fps = len(self.fps_history) / (current_time - fps_start_time + 1e-6)
                else:
                    fps = 0
                
                self.fps_history.append(current_time)
                
                if len(self.fps_history) == 1:
                    fps_start_time = current_time
                
                # PPE analysis
                ppe_status = self.analyze_ppe_ultra_fast(detections)
                
                # Draw overlay
                display_frame = self.draw_ultra_fast_overlay(frame, detections, ppe_status, fps)
                
                # Display
                cv2.imshow('Ultra-Fast PPE Detection', display_frame)
                
                # Handle keys
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.fps_history.clear()
                    self.frame_count = 0
                    self.detection_count = 0
                    fps_start_time = time.time()
                    logger.info("Stats reset")
                
                self.frame_count += 1
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        
        finally:
            # Cleanup
            self.running = False
            if self.detection_thread:
                self.detection_thread.join(timeout=1)
            cap.release()
            cv2.destroyAllWindows()
            
            # Final stats
            total_time = time.time() - fps_start_time
            avg_fps = self.frame_count / total_time if total_time > 0 else 0
            
            logger.info("="*50)
            logger.info("ULTRA-FAST DETECTION STATS")
            logger.info(f"Total frames: {self.frame_count}")
            logger.info(f"Total detections: {self.detection_count}")
            logger.info(f"Average FPS: {avg_fps:.1f}")
            logger.info(f"Last inference time: {self.last_detection_time*1000:.1f}ms")
            
            if avg_fps >= 30:
                logger.info("🎯 TARGET ACHIEVED: 30+ FPS!")
            elif avg_fps >= 25:
                logger.info("🎉 EXCELLENT: 25+ FPS!")
            elif avg_fps >= 20:
                logger.info("✅ GOOD: 20+ FPS!")
            else:
                logger.info("⚠️ NEEDS OPTIMIZATION: <20 FPS")
            
            logger.info("="*50)
        
        return True

def main():
    """Main function"""
    print("🚀 ULTRA-FAST PPE DETECTION SYSTEM")
    print("=" * 50)
    print("🎯 Target: 30+ FPS")
    print("⚡ Extreme optimizations enabled")
    print("🔧 Settings: 80x80 input, 12x frame skip")
    print("=" * 50)
    
    detector = UltraFastPPEDetector()
    
    try:
        success = detector.run_ultra_fast_detection()
        if success:
            print("✅ Ultra-fast detection completed successfully!")
        else:
            print("❌ Ultra-fast detection failed!")
    except Exception as e:
        logger.error(f"System error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    main() 