# my_simple_pipeline.py 

import cv2
import time
from collections import deque
import torch
from ultralytics import YOLO

class SimpleDetectionPipeline:
    def __init__(self):
        # Model setup
        torch.set_default_device('cpu')
        self.model = YOLO('yolov8n.pt')
        self.model.to('cpu')
        
        # Performance monitoring
        self.fps_queue = deque(maxlen=30)
        
    def detect_objects(self, frame):
        """Basit detection"""
        results = self.model(frame, conf=0.5, verbose=False)
        
        detections = []
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().numpy()
                class_ids = result.boxes.cls.cpu().numpy().astype(int)
                
                for i in range(len(boxes)):
                    x1, y1, x2, y2 = boxes[i].astype(int)
                    confidence = confidences[i]
                    class_name = self.model.names[class_ids[i]]
                    
                    detections.append({
                        'bbox': (x1, y1, x2, y2),
                        'confidence': confidence,
                        'class_name': class_name
                    })
        
        return detections
    
    def draw_detections(self, frame, detections):
        """Basit çizim"""
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            confidence = det['confidence']
            class_name = det['class_name']
            
            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            
            # Label
            label = f"{class_name}: {confidence:.2f}"
            cv2.putText(frame, label, (x1, y1-10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return frame
    
    def run_detection(self, source=0):
        """ANA PIPELINE - BU ÖNEMLİ!"""
        
        # 📹 VIDEO SETUP
        cap = cv2.VideoCapture(source)
        
        if not cap.isOpened():
            print("❌ Kamera açılamadı!")
            return
        
        print("🎥 Simple Detection Pipeline başladı!")
        print("q = çık, s = stats göster")
        
        frame_count = 0
        
        # ♾️ ANA DÖNGÜ
        while True:
            # ⏱️ Performance başlat
            start_time = time.time()
            
            # 🖼️ FRAME OKU
            ret, frame = cap.read()
            if not ret:
                print("❌ Frame okunamadı!")
                break
            
            frame_count += 1
            
            # 🎯 DETECTION PIPELINE:
            
            # 1. DETECT
            detections = self.detect_objects(frame)
            
            # 2. DRAW (tracking yok şimdilik)
            frame = self.draw_detections(frame, detections)
            
            # 3. PERFORMANCE
            frame_time = time.time() - start_time
            self.fps_queue.append(frame_time)
            
            # 4. FPS GÖSTER
            if len(self.fps_queue) > 0:
                current_fps = 1.0 / (sum(self.fps_queue) / len(self.fps_queue))
                cv2.putText(frame, f"FPS: {current_fps:.1f}", (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
            
            cv2.putText(frame, f"Frame: {frame_count}", (10, 70), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # 📺 GÖSTER
            cv2.imshow('Simple Detection Pipeline', frame)
            
            # ⌨️ INPUT HANDLING
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                print(f"\n📊 STATS:")
                print(f"  Frame: {frame_count}")
                print(f"  FPS: {current_fps:.1f}")
                print(f"  Detections: {len(detections)}")
        
        # 🧹 CLEANUP
        cap.release()
        cv2.destroyAllWindows()
        print("✅ Pipeline tamamlandı!")

# Test et
if __name__ == "__main__":
    pipeline = SimpleDetectionPipeline()
    
    print("🎯 SIMPLE DETECTION PIPELINE")
    print("1. Webcam test")
    print("2. Video file test") 
    
    choice = input("Seçim (1-2): ")
    
    if choice == "1":
        pipeline.run_detection(0)  # Webcam
    elif choice == "2":
        video_path = input("Video path: ")
        pipeline.run_detection(video_path)