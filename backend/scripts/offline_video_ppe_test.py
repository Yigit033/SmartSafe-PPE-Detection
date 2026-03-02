import argparse
import os
import sys
from typing import List, Optional

import cv2

# Ensure project root (one level above scripts/) is on sys.path so that `src.*` imports work
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.smartsafe.api.smartsafe_saas_api import SmartSafeSaaSAPI  # type: ignore
from src.smartsafe.detection.pose_aware_ppe_detector import get_pose_aware_detector  # type: ignore
from src.smartsafe.detection.utils.visual_overlay import draw_styled_box, get_class_color  # type: ignore


# Varsayılan test videosu (proje köküne göre göreli yol)
DEFAULT_VIDEO_PATH = os.path.join("tests", "Videos", "insaat01.mp4")


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
        "--no-window",
        action="store_true",
        help="Disable OpenCV window display (only logs).",
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

        company_ppe_config = api.db.get_company_ppe_config(company_id)
        if isinstance(company_ppe_config, dict) and "required" in company_ppe_config:
            raw_required = company_ppe_config.get("required")
            if isinstance(raw_required, list):
                normalized: List[str] = []
                for item in raw_required:
                    if item is None:
                        continue
                    try:
                        normalized.append(str(item).strip().lower())
                    except Exception:
                        continue
                return normalized
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

    # Initialize SaaS API and pose-aware detector so that we reuse the same models and config
    api = SmartSafeSaaSAPI()
    pose_detector = get_pose_aware_detector(ppe_detector=api.sh17_manager)

    # Resolve sector and required PPE from company config (same logic as SaaS worker)
    if api.db is not None:
        company_data = api.db.get_company_info(args.company_id)
        sector = (
            company_data.get("sector", "construction")
            if company_data and isinstance(company_data, dict)
            else "construction"
        )
    else:
        sector = "construction"

    required_ppe = get_required_ppe_for_company(api, args.company_id)

    frame_idx = 0
    window_name = f"PPE Test - {os.path.basename(args.video)} ({sector})"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if args.skip > 1 and frame_idx % args.skip != 0:
            continue

        result = pose_detector.detect_with_pose(
            frame,
            sector=sector,
            confidence=args.confidence,
            required_ppe=required_ppe,
        )

        detections = result.get("detections", [])

        # Draw persons and PPE boxes using the same visual style utilities
        annotated = frame.copy()
        for det in detections:
            bbox = det.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = bbox
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
        people = result.get("people_detected", 0)
        compliant = result.get("compliant_people", 0)
        compliance_rate = result.get("compliance_rate", 0)
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

