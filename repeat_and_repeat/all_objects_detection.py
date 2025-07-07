# all_objects_detection.py - YENİ DOSYA


import cv2
import numpy as np
from ultralytics import YOLO
import torch



# benim_detection_advanced.py - YENI DOSYA OLUŞTUR

import cv2
import numpy as np
from ultralytics import YOLO
import torch

def test_different_confidence():
    """Farklı confidence değerlerini test et"""
    
    # Model setup
    torch.set_default_device('cpu')
    model = YOLO('yolov8s.pt')
    model.to('cpu')
    
    cap = cv2.VideoCapture(0)
    
    # FARKLI CONFIDENCE DEĞERLERİ
    confidence_levels = [0.1, 0.3, 0.5, 0.7, 0.9]
    current_conf_index = 0
    
    print("🎯 CONFIDENCE THRESHOLD TEST")
    print("Space tuşuna bas = confidence değiştir")
    print("q tuşuna bas = çık")
    
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        current_conf = confidence_levels[current_conf_index]
        
        # Her 10 frame'de detection
        if frame_count % 5 == 0:
            print(f"\n--- CONFIDENCE: {current_conf} ---")
            
            # FARKLI CONFIDENCE İLE TEST
            results = model(frame, conf=current_conf, verbose=False)
            
            if results and len(results) > 0:
                result = results[0]
                
                if result.boxes is not None:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    confidences = result.boxes.conf.cpu().numpy()
                    class_ids = result.boxes.cls.cpu().numpy().astype(int)
                    
                    print(f"🎯 {len(boxes)} nesne tespit edildi:")
                    
                    for i in range(len(boxes)):
                        x1, y1, x2, y2 = boxes[i].astype(int)
                        confidence = confidences[i]
                        class_id = class_ids[i]
                        class_name = model.names[class_id]
                        
                        print(f"  {class_name}: {confidence:.3f}")
                        
                        # Renk: Yeşil=yüksek güven, Kırmızı=düşük güven
                        color = (0, 255, 0) if confidence > 0.7 else (0, 255, 255) if confidence > 0.5 else (0, 0, 255)
                        
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        label = f"{class_name}: {confidence:.2f}"
                        cv2.putText(frame, label, (x1, y1-10), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                else:
                    print("❌ Hiçbir nesne tespit edilmedi")
        
        # UI bilgileri
        cv2.putText(frame, f"Confidence: {current_conf}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        cv2.putText(frame, "SPACE=Change Conf, Q=Quit", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        cv2.imshow('Confidence Test', frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord(' '):  # Space tuşu
            current_conf_index = (current_conf_index + 1) % len(confidence_levels)
            print(f"\n🔄 Confidence değiştirildi: {confidence_levels[current_conf_index]}")
    
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    test_different_confidence()