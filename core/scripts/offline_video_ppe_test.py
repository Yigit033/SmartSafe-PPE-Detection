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


# Varsayılan test videosu (proje köküne göre göreli yol)
DEFAULT_VIDEO_PATH = os.path.join(PROJECT_ROOT, "tests", "Videos", "food.mp4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline video PPE detection test using the same pipeline as SaaS pose-aware detection."
    )
    parser.add_argument(
        "--video",
        "-v",
        default=DEFAULT_VIDEO_PATH,
        help=f"Path to input video file (default: {DEFAULT_VIDEO_PATH})",
    )
    parser.add_argument(
        "--company-id",
        "-c",
        default="demo_20260301_200734",
        help="Company ID to resolve sector and PPE config (defaults to demo_company).",
    )
    parser.add_argument(
        "--confidence",
        "-conf",
        type=float,
        default=0.5,
        help="Detection confidence threshold (default: 0.5).",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=3,
        help="Process every Nth frame (default: 3) for speed.",
    )
    parser.add_argument(
        "--debug-raw",
        action="store_true",
        help="Log raw SH17 detections for the first few processed frames to analyze model behaviour.",
    )
    parser.add_argument(
        "--raw-conf",
        type=float,
        default=0.3,
        help="Confidence threshold used when logging raw SH17 detections (default: 0.3).",
    )
    parser.add_argument(
        "--debug-frames",
        type=int,
        default=5,
        help="Number of frames to log raw detections for when --debug-raw is enabled (default: 5).",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Disable OpenCV window display (only logs).",
    )
    parser.add_argument(
        "--sector",
        type=str,
        default=None,
        help="Override company sector (e.g., food, construction)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Force device (cpu or cuda). If None, automatic.",
    )
    return parser.parse_args()


def get_required_ppe_for_company(api: SmartSafeSaaSAPI, company_id: str) -> Optional[List[str]]:
    """
    Read company's PPE configuration from the same DB path used by SaaS.
    Returns a normalized required PPE list or None if config is not defined.
    """
    try:
        if api.db is None:
            return None

        import json
        company_info = api.db.get_company_info(company_id)
        if not company_info or not isinstance(company_info, dict):
            return None

        # required_ppe is stored as a JSON string in the companies table
        raw_ppe = company_info.get("required_ppe")
        if raw_ppe is None:
            return None

        # Parse JSON if it's a string
        if isinstance(raw_ppe, str):
            try:
                raw_ppe = json.loads(raw_ppe)
            except (json.JSONDecodeError, ValueError):
                return None

        if isinstance(raw_ppe, list):
            normalized: List[str] = []
            for item in raw_ppe:
                if item is None:
                    continue
                try:
                    normalized.append(str(item).strip().lower())
                except Exception:
                    continue
            return normalized if normalized else None

        # If it's a dict with a "required" key (legacy format)
        if isinstance(raw_ppe, dict) and "required" in raw_ppe:
            raw_required = raw_ppe.get("required")
            if isinstance(raw_required, list):
                normalized = []
                for item in raw_required:
                    if item is None:
                        continue
                    try:
                        normalized.append(str(item).strip().lower())
                    except Exception:
                        continue
                return normalized if normalized else None

        return None
    except Exception:
        return None


def main() -> None:
    args = parse_args()

    if not os.path.exists(args.video):
        raise FileNotFoundError(f"Video file not found: {args.video}")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {args.video}")

    # Initialize SaaS API (without starting the Flask server) to reuse models and config
    api = SmartSafeSaaSAPI()
    
    # Device Override
    if args.device:
        print(f"🖥️  Forcing device: {args.device}")
        api.sh17_manager.device = args.device
        if hasattr(api.sh17_manager, 'models'):
            for m in api.sh17_manager.models.values():
                m.to(args.device)
    
    api.ensure_database_initialized()
    pose_detector = get_pose_aware_detector(ppe_detector=api.sh17_manager)
    
    if args.device and hasattr(pose_detector, 'pose_model'):
        pose_detector.pose_model.to(args.device)

    # Resolve sector and required PPE from company config (same logic as SaaS worker)
    # Sector Override Logic
    if args.sector:
        sector = args.sector
        print(f"📌 Sector overridden by command line: {sector}")
    elif api.db is not None:
        company_data = api.db.get_company_info(args.company_id)
        sector = (
            company_data.get("sector", "construction")
            if company_data and isinstance(company_data, dict)
            else "construction"
        )
    else:
        sector = "construction"

    required_ppe = get_required_ppe_for_company(api, args.company_id)
    
    # Gıda Sektörü İçin Gerekli PPE Varsayılanları
    if sector in ('food', 'food_beverage') and not required_ppe:
        # Food modelinin tespit edebildiği sınıflar
        required_ppe = ['apron', 'haircap', 'gloves', 'face_mask_medical', 'glasses']
        print(f"🍽️  Food sector detected. Using default food PPE requirements: {required_ppe}")

    print(f"🚀 Starting test for Sector: {sector}")
    if required_ppe:
        print(f"📋 Required PPE: {required_ppe}")

    frame_idx = 0
    start_time = time.time()
    first_helmet_time: Optional[float] = None
    first_helmet_frame: Optional[int] = None
    window_name = f"PPE Test - {os.path.basename(args.video)} ({sector})"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if args.skip > 1 and frame_idx % args.skip != 0:
            continue

        # Downscale frame for faster inference; bbox'ları sonra orijinale map edeceğiz.
        orig_h, orig_w = frame.shape[:2]
        scale = 0.5
        small_w, small_h = int(orig_w * scale), int(orig_h * scale)
        frame_small = cv2.resize(frame, (small_w, small_h))

        # Optional: inspect raw SH17 detections for the first few frames
        if args.debug_raw and frame_idx <= args.debug_frames:
            raw = api.sh17_manager.detect_ppe(frame_small, sector=sector, confidence=args.raw_conf)
            ppe_classes = [
                "helmet",
                "safety_vest",
                "safety_suit",
                "shoes",
                "gloves",
                "glasses",
                "face_mask_medical",
            ]
            interesting = [
                {
                    "cls": d.get("class_name"),
                    "conf": round(float(d.get("confidence", 0.0)), 3),
                    # Map bbox back to original resolution for easier interpretation
                    "bbox": [
                        round(float(d.get("bbox", [])[0]) / scale, 1) if len(d.get("bbox", [])) == 4 else None,
                        round(float(d.get("bbox", [])[1]) / scale, 1) if len(d.get("bbox", [])) == 4 else None,
                        round(float(d.get("bbox", [])[2]) / scale, 1) if len(d.get("bbox", [])) == 4 else None,
                        round(float(d.get("bbox", [])[3]) / scale, 1) if len(d.get("bbox", [])) == 4 else None,
                    ],
                    "model_type": d.get("model_type"),
                }
                for d in raw
                if d.get("class_name") in ppe_classes
            ]
            print(
                f"[RAW-SH17] frame={frame_idx} total={len(raw)} "
                f"ppe={len(interesting)} details={interesting}"
            )

        # Hafif mod: SH17 her 3 frame'de bir çalışsın, aradaki frame'lerde cache kullansın.
        try:
            pose_detector.sh17_every_n = 3
        except Exception:
            # Eski versiyonlarla uyum için sessizce geç
            pass

        result = pose_detector.detect_with_pose(
            frame_small,
            sector=sector,
            confidence=args.confidence,
            required_ppe=required_ppe,
        )

        # Pose-aware dedektör normalde dict döner; ancak pose modeli kişi bulamazsa
        # SH17'nin standart list çıktısına geri düşebilir. Her iki formata da uyum sağla.
        if isinstance(result, list):
            detections = result
            people = sum(
                1
                for d in detections
                if str(d.get("class_name", "")).lower() == "person"
            )
            compliant = 0
            compliance_rate = 0.0
        else:
            detections = result.get("detections", [])
            people = result.get("people_detected", 0)
            compliant = result.get("compliant_people", 0)
            compliance_rate = float(result.get("compliance_rate", 0.0))

        # İlk kaskın ne zaman bulunduğunu ölç (sadece bir kere logla)
        if first_helmet_time is None and detections:
            for det in detections:
                cname = str(det.get("class_name", "")).lower()
                if any(k in cname for k in ["helmet", "hard_hat", "hardhat", "baret"]):
                    first_helmet_time = time.time() - start_time
                    first_helmet_frame = frame_idx
                    print(
                        f"[METRIC] First helmet detected at frame={first_helmet_frame}, "
                        f"t={first_helmet_time:.2f}s since start"
                    )
                    break

        # Draw persons and PPE boxes using the same visual style utilities
        annotated = frame.copy()
        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            # Bbox'lar küçük çözünürlükte; orijinal frame'e çizmek için tekrar ölçekle
            x1, y1, x2, y2 = bbox
            x1 = int(x1 / scale)
            y1 = int(y1 / scale)
            x2 = int(x2 / scale)
            y2 = int(y2 / scale)
            class_name = str(det.get("class_name", ""))
            is_missing = bool(det.get("missing", False))
            color = get_class_color(class_name, is_missing=is_missing)
            annotated = draw_styled_box(
                annotated,
                int(x1),
                int(y1),
                int(x2),
                int(y2),
                f"{class_name}",
                color,
            )

        # Small HUD with summary
        text = f"People: {people} | Compliant: {compliant} | Compliance: {compliance_rate:.1f}%"
        cv2.putText(
            annotated,
            text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        if not args.no_window:
            cv2.imshow(window_name, annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    if not args.no_window:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

