"""
🍽️ SmartSafe AI - Gıda Sektörü Özel Video PPE Test Scripti
============================================================
Gıda üretim tesislerinde kullanılan özel PPE ekipmanlarını
(Bone, Önlük, Maske, Gözlük, Eldiven) tespit eden test aracı.

Kullanım:
  python core/scripts/food_sector_video_test.py
  python core/scripts/food_sector_video_test.py --video path/to/video.mp4
  python core/scripts/food_sector_video_test.py --device cpu   (VRAM düşükse)
"""

import argparse
import os
import sys
import time
from typing import List, Optional

import cv2
import numpy as np

# Proje kökünü sys.path'e ekle (scripts/ dizininin bir üstü = core/)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import SmartSafeSaaSAPI  # type: ignore
from detection.pose_aware_ppe_detector import get_pose_aware_detector  # type: ignore
from detection.utils.visual_overlay import draw_styled_box, get_class_color  # type: ignore

# Varsayılan gıda sektörü test videosu
DEFAULT_VIDEO_PATH = os.path.join(PROJECT_ROOT, "tests", "Videos", "food.mp4")

# ── Gıda Sektörü PPE Gereksinimleri ─────────────────────────────────────────
# Bu isimler SH17ModelManager._FOOD_PPE_NAME_MAP tarafından
# food modelin çıktısından dönüştürülen canonical isimlerdir:
#   Apron   → medical_suit   (PPE_CONFIG: safety_suit)
#   Haircap → haircap        (PPE_CONFIG: haircap)
#   Mask    → face_mask_medical (PPE_CONFIG: face_mask)
#   Googles → glasses        (PPE_CONFIG: safety_glasses)
#   gloves  → gloves         (PPE_CONFIG: gloves)
FOOD_REQUIRED_PPE = [
    "safety_suit",       # Apron / Önlük
    "haircap",           # Bone / Saç filesi
    "face_mask",         # Maske
    "safety_glasses",    # Gözlük (Googles/Goggles)
    "gloves",            # Eldiven
]

# Türkçe etiket haritası (ekranda gösterilecek isimler)
# Compliance sistemi PPE_CONFIG'deki pos_label / neg_label değerlerini döndürür,
# bu yüzden hem canonical hem display isimlerini ekliyoruz.
FOOD_LABEL_MAP = {
    # Canonical (model çıktısı) isimler
    "medical_suit":      "Onluk",
    "safety_suit":       "Onluk",
    "apron":             "Onluk",
    "haircap":           "Bone",
    "face_mask_medical": "Maske",
    "face_mask":         "Maske",
    "mask":              "Maske",
    "glasses":           "Gozluk",
    "safety_glasses":    "Gozluk",
    "googles":           "Gozluk",
    "goggles":           "Gozluk",
    "gloves":            "Eldiven",
    "person":            "Personel",
    "head":              "Bas",

    # PPE_CONFIG pos_label değerleri (compliance sistemi bunları döndürür)
    "safety suit":       "Onluk",
    "helmet":            "Baret",
    "safety vest":       "Yelek",
    "safety shoes":      "Ayakkabi",
    "safety glasses":    "Gozluk",
    "face mask":         "Maske",

    # PPE_CONFIG neg_label değerleri
    "no-suit":           "Onluk YOK",
    "no-haircap":        "Bone YOK",
    "no-helmet":         "Baret YOK",
    "no-vest":           "Yelek YOK",
    "no-shoes":          "Ayakkabi YOK",
    "no-glasses":        "Gozluk YOK",
    "no-mask":           "Maske YOK",
    "no-gloves":         "Eldiven YOK",
}

# Gıda sektörüne özel renk paleti (BGR)
FOOD_COLOR_MAP = {
    "medical_suit":      (180, 105, 255),  # Pembe-mor (önlük)
    "safety_suit":       (180, 105, 255),
    "apron":             (180, 105, 255),
    "haircap":           (255, 200, 0),    # Açık mavi (bone)
    "face_mask_medical": (0, 200, 200),    # Sarı-yeşil (maske)
    "face_mask":         (0, 200, 200),
    "mask":              (0, 200, 200),
    "glasses":           (255, 150, 50),   # Açık mavi (gözlük)
    "safety_glasses":    (255, 150, 50),
    "googles":           (255, 150, 50),
    "gloves":            (255, 255, 0),    # Cyan (eldiven)
    "person":            (50, 160, 255),   # Turuncu-mavi (personel)
}
MISSING_COLOR = (0, 0, 255)  # Kırmızı (eksik ekipman)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SmartSafe AI - Gıda Sektörü Özel Video PPE Test Scripti"
    )
    parser.add_argument(
        "--video", "-v",
        default=DEFAULT_VIDEO_PATH,
        help=f"Video dosyası yolu (varsayılan: {DEFAULT_VIDEO_PATH})",
    )
    parser.add_argument(
        "--confidence", "-conf",
        type=float, default=0.40,
        help="Güven eşiği (varsayılan: 0.40)",
    )
    parser.add_argument(
        "--skip",
        type=int, default=2,
        help="Her N frame'de bir işle (hız için, varsayılan: 2)",
    )
    parser.add_argument(
        "--device",
        type=str, default=None,
        help="Cihaz seçimi: 'cpu' veya 'cuda' (varsayılan: otomatik)",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Görüntü penceresini açma (sadece log bas)",
    )
    return parser.parse_args()


def get_food_color(class_name: str, is_missing: bool = False) -> tuple:
    """Gıda sektörüne özel renk döndür."""
    if is_missing:
        return MISSING_COLOR
    return FOOD_COLOR_MAP.get(class_name.lower(), (180, 180, 180))


def main() -> None:
    args = parse_args()

    # ── Video Dosyası Kontrolü ───────────────────────────────────────────
    video_path = args.video
    if not os.path.exists(video_path):
        # Proje köküne göre dene
        video_path = os.path.join(PROJECT_ROOT, args.video)

    if not os.path.exists(video_path):
        print(f"❌ Video bulunamadı: {args.video}")
        print(f"   Lütfen videoyu şu dizine koyun: {os.path.join(PROJECT_ROOT, 'tests', 'Videos')}")
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Video açılamadı: {video_path}")
        return

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    print("=" * 60)
    print("🍽️  SmartSafe - Gıda Sektörü PPE Testi")
    print("=" * 60)
    print(f"📹 Video    : {video_path}")
    print(f"📊 Toplam   : {total_frames} frame ({fps:.1f} FPS)")
    print(f"🎯 Sektör   : food (Gıda Üretimi)")
    print(f"📋 Gerekli  : {', '.join(FOOD_REQUIRED_PPE)}")
    print(f"🎚️  Güven    : {args.confidence}")
    print(f"⏭️  Frame Skip: {args.skip}")
    if args.device:
        print(f"🖥️  Cihaz    : {args.device}")
    print("=" * 60)

    # ── SaaS API + Model Başlatma ────────────────────────────────────────
    api = SmartSafeSaaSAPI()

    # Device override (CUDA OOM hatalarını önlemek için)
    if args.device:
        api.sh17_manager.device = args.device
        if hasattr(api.sh17_manager, 'models'):
            for m in api.sh17_manager.models.values():
                m.to(args.device)

    api.ensure_database_initialized()

    # Pose dedektörü al
    pose_detector = get_pose_aware_detector(ppe_detector=api.sh17_manager)

    if args.device and hasattr(pose_detector, 'pose_model') and pose_detector.pose_model is not None:
        pose_detector.pose_model.to(args.device)

    # SH17'yi her 3 frame'de bir çalıştır (performans)
    try:
        pose_detector.sh17_every_n = 3
    except Exception:
        pass

    print("\n🚀 Test başlatılıyor...\n")

    # ── Video İşleme Döngüsü ────────────────────────────────────────────
    frame_idx = 0
    processed = 0
    start_time = time.time()
    window_name = f"SmartSafe Food PPE - {os.path.basename(video_path)}"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if args.skip > 1 and frame_idx % args.skip != 0:
            continue

        processed += 1

        # Ölçekleme (hız için)
        orig_h, orig_w = frame.shape[:2]
        scale = 0.5
        small_w, small_h = int(orig_w * scale), int(orig_h * scale)
        frame_small = cv2.resize(frame, (small_w, small_h))

        # ── Tespit ──────────────────────────────────────────────────────
        result = pose_detector.detect_with_pose(
            frame_small,
            sector="food",
            confidence=args.confidence,
            required_ppe=FOOD_REQUIRED_PPE,
        )

        # Sonuç ayrıştırma
        if isinstance(result, list):
            detections = result
            people = sum(
                1 for d in detections
                if str(d.get("class_name", "")).lower() == "person"
            )
            compliant = 0
            compliance_rate = 0.0
        else:
            detections = result.get("detections", [])
            people = result.get("people_detected", 0)
            compliant = result.get("compliant_people", 0)
            compliance_rate = float(result.get("compliance_rate", 0.0))

        # ── Görselleştirme ──────────────────────────────────────────────
        annotated = frame.copy()

        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) != 4:
                continue

            x1, y1, x2, y2 = bbox
            # Bbox'ları orijinal boyuta geri ölçekle
            x1 = int(x1 / scale)
            y1 = int(y1 / scale)
            x2 = int(x2 / scale)
            y2 = int(y2 / scale)

            class_name = str(det.get("class_name", ""))
            is_missing = bool(det.get("missing", False))
            conf = det.get("confidence", 0.0)
            model_type = det.get("model_type", "")

            # Türkçe etiket
            display_name = FOOD_LABEL_MAP.get(class_name.lower(), class_name)
            if is_missing:
                display_name = f"[X] EKSIK: {display_name}"

            # Güven skoru ekle
            if conf and not is_missing:
                display_name = f"{display_name} ({conf:.0%})"

            # Model tipini logla (ilk 5 frame)
            if processed <= 5 and model_type:
                print(f"  [{model_type}] {class_name} → {display_name} (conf={conf:.2f})")

            color = get_food_color(class_name, is_missing=is_missing)
            annotated = draw_styled_box(annotated, x1, y1, x2, y2, display_name, color)

        # ── HUD (Bilgi Paneli) ──────────────────────────────────────────
        # Üstte yarı saydam bilgi bandı
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (orig_w, 70), (0, 0, 0), -1)
        annotated = cv2.addWeighted(overlay, 0.5, annotated, 0.5, 0)

        # Compliance rengi
        if compliance_rate >= 80:
            comp_color = (0, 255, 0)
        elif compliance_rate >= 50:
            comp_color = (0, 200, 255)
        else:
            comp_color = (0, 0, 255)

        hud_line1 = f"GIDA SEKTORU | Personel: {people} | Uygun: {compliant}/{people}"
        hud_line2 = f"Uygunluk: %{compliance_rate:.1f} | Frame: {frame_idx}/{total_frames}"
        cv2.putText(annotated, hud_line1, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        cv2.putText(annotated, hud_line2, (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.55, comp_color, 2)

        # Periyodik konsol logu
        if processed % 50 == 0:
            elapsed = time.time() - start_time
            real_fps = processed / elapsed if elapsed > 0 else 0
            print(
                f"[Frame {frame_idx:>5}/{total_frames}] "
                f"Personel={people} Uygunluk=%{compliance_rate:.1f} "
                f"({real_fps:.1f} FPS)"
            )

        if not args.no_window:
            cv2.imshow(window_name, annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print("\n⏹️  Kullanıcı tarafından durduruldu.")
                break

    # ── Özet ─────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("📊 Test Özeti")
    print("=" * 60)
    print(f"  Toplam Frame : {frame_idx}")
    print(f"  İşlenen      : {processed}")
    print(f"  Süre          : {elapsed:.1f}s")
    print(f"  Ortalama FPS  : {processed / elapsed:.1f}" if elapsed > 0 else "  Ortalama FPS  : N/A")
    print("=" * 60)

    cap.release()
    if not args.no_window:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
