import argparse
import os
import sys
import time
from typing import List, Optional

import cv2

# Ensure project root (one level above scripts/) is on sys.path so that `src.*` imports work
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import SmartSafeSaaSAPI  # type: ignore
from detection.pose_aware_ppe_detector import get_pose_aware_detector  # type: ignore
from detection.utils.visual_overlay import draw_styled_box, get_class_color  # type: ignore


# Varsayılan gıda sektörü test videosu
DEFAULT_VIDEO_PATH = os.path.join("tests", "Videos", "video002.mp4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SmartSafe AI - Gıda Sektörü Özel Video PPE Test Scripti"
    )
    parser.add_argument(
        "--video",
        "-v",
        default=DEFAULT_VIDEO_PATH,
        help=f"Video dosyası yolu (varsayılan: {DEFAULT_VIDEO_PATH})",
    )
    parser.add_argument(
        "--confidence",
        "-conf",
        type=float,
        default=0.45,
        help="Güven eşiği (varsayılan: 0.45)",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=2,
        help="Her N frame'de bir işle (hız için, varsayılan: 2)",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Görüntü penceresini açma (sadece log bas)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Video dosyasını kontrol et (hem mutlak hem göreli yol)
    video_path = args.video
    if not os.path.exists(video_path):
        # Proje köküne göre dene
        video_path = os.path.join(PROJECT_ROOT, args.video)
        
    if not os.path.exists(video_path):
        print(f"❌ Video bulunamadı: {args.video}")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Video açılamadı: {video_path}")
        return

    print(f"🚀 Gıda Sektörü Testi Başlatılıyor...")
    print(f"📹 Video: {video_path}")
    print(f"🎯 Sektör: food")

    # SaaS API'yi başlat (modelleri ve veritabanını yüklemek için)
    api = SmartSafeSaaSAPI()
    api.ensure_database_initialized()
    
    # Gıda sektörü için dedektörü al
    # Not: Factory'de yaptığımız güncelleme sayesinde 'food' sektörü için özel model yüklenecek.
    pose_detector = get_pose_aware_detector(ppe_detector=api.sh17_manager)

    # Gıda sektörü için zorunlu ekipmanlar
    required_ppe = ["hairnet", "face_mask", "apron"]
    
    frame_idx = 0
    start_time = time.time()
    window_name = f"SmartSafe Food Safety Test - {os.path.basename(video_path)}"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if args.skip > 1 and frame_idx % args.skip != 0:
            continue

        # Görüntüyü işle
        # Orijinal boyutta veya ölçeklendirilmiş boyutta işlenebilir
        orig_h, orig_w = frame.shape[:2]
        scale = 0.6  # İşleme hızı için %60 ölçekleme
        small_w, small_h = int(orig_w * scale), int(orig_h * scale)
        frame_small = cv2.resize(frame, (small_w, small_h))

        # Tespit yap
        result = pose_detector.detect_with_pose(
            frame_small,
            sector="food",
            confidence=args.confidence,
            required_ppe=required_ppe,
        )

        detections = []
        people = 0
        compliant = 0
        compliance_rate = 0.0

        if isinstance(result, list):
            detections = result
            people = sum(1 for d in detections if str(d.get("class_name", "")).lower() == "person")
        else:
            detections = result.get("detections", [])
            people = result.get("people_detected", 0)
            compliant = result.get("compliant_people", 0)
            compliance_rate = float(result.get("compliance_rate", 0.0))

        # Çizim Yap
        annotated = frame.copy()
        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            
            x1, y1, x2, y2 = bbox
            # Bbox'ları orijinal boyuta geri ölçekle
            x1, y1, x2, y2 = int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale)
            
            class_name = str(det.get("class_name", ""))
            is_missing = bool(det.get("missing", False))
            
            # Türkçe etiketler için mapping
            label_map = {
                "hairnet": "Bone",
                "face_mask": "Maske",
                "face_mask_medical": "Maske",
                "apron": "Onluk",
                "gloves": "Eldiven",
                "person": "Personel"
            }
            display_name = label_map.get(class_name.lower(), class_name)
            
            if is_missing:
                display_name = f"EKSIK: {display_name}"
            
            color = get_class_color(class_name, is_missing=is_missing)
            annotated = draw_styled_box(annotated, x1, y1, x2, y2, display_name, color)

        # HUD (Bilgi Paneli)
        hud_text = f"Personel: {people} | Uygunluk: %{compliance_rate:.1f}"
        cv2.putText(annotated, hud_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        if not args.no_window:
            cv2.imshow(window_name, annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    print(f"✅ Test tamamlandı. Toplam {frame_idx} frame işlendi.")
    cap.release()
    if not args.no_window:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
