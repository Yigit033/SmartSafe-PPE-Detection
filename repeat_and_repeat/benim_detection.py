
import cv2
import numpy as np
from ultralytics import YOLO
import torch


def my_simple_detection():
    """Kendi basit detection fonksiyonum"""

    print("Model Yükleniyor")
    torch.set_default_device("cpu")
    model = YOLO("yolov8n.pt")
    model.to("cpu")


    print("Kamera açılmak üzere...")
    cap = cv2.VideoCapture(0)


    if not cap.isOpened():
        print("Kamera açılamıyor, tekara deneyiniz...")
        return
    
    print("🎉 Hazır! 'q' tuşuna basarak çık")
    print("📝 Konsolu izle - tespit edilen nesneler yazılacak")

    frame_count = 0


    while True:
        ret, frame = cap.read()
        if not ret:
            print("Kamera okunamadı, tekrar deneyiniz...")
            break

        frame_count +=1

        if frame_count % 10 == 0:
            results = model(frame, conf=0.5, verbose=False)

            print(f"\n--- Frame {frame_count} ---")


            if results and len(results) > 0:
                results = results[0]

                if results.boxes is not None:

                    boxes = results.boxes.xyxy.cpu().numpy()
                    confidences = results.boxes.conf.cpu().numpy()
                    class_ids = results.boxes.cls.cpu().numpy().astype(int) 

                    print(f"🔍 {len(boxes)} nesne tespit edildi")

                    for i in range(len(boxes)):
                        x1, y1, x2, y2 = boxes[i].astype(int)
                        confidence = confidences[i]
                        class_id = class_ids[i]
                        class_name = model.names[class_id]

                        print(f"🎯 {class_name} - Güven: {confidence:.2f} ({x1},{y1},{x2},{y2})")


                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)


                        label = f"{class_name}: {confidence:.2f}"
                        cv2.putText(frame, label, (x1, y1-10), cv2.FONT_HERSHEY_COMPLEX, 0.7, (0, 255, 0), 2)
                    
                    else:
                        print("🔍 Hiçbir nesne tespit edilmedi")

                else:
                    print("❌ YOLO sonuç vermedi")




        # Frame info ekle
        cv2.putText(frame, f"Frame: {frame_count}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
        cv2.putText(frame, "My Simple Detector", (10, 70), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 255), 2)
        

        cv2.imshow("My Simple Detection", frame)

        # Çıkış Kontrolü

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break


    cap.release()
    cv2.destroyAllWindows()
    print("Detection tamamlandı")

if __name__ == "__main__":
    my_simple_detection()