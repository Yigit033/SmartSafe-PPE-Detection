from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_violation_debug_meta(
    *,
    camera_key: str,
    camera_id: str,
    company_id: str,
    frame_shape: Optional[List[int]],
    person_visible: bool,
    event_person_bbox: Any,
    results: Any,
    decision_summary: Any,
    roi_on: Any,
    roi_stats: Any,
    temporal_missing_by_type_json: Any,
    temporal_stats_by_type: Any,
    ppe_violations_before: Any,
    ppe_violations_after: Any,
    frame_skip: int,
    processing_time_ms: Optional[float],
) -> Dict[str, Any]:
    # NOTE: This is intentionally lightweight and JSON-friendly.
    # Any deep sanitization is handled in the DB layer.

    def _iou_bbox(a, b) -> float:
        try:
            ax1, ay1, ax2, ay2 = [float(x) for x in a]
            bx1, by1, bx2, by2 = [float(x) for x in b]
        except Exception:
            return 0.0
        x1 = max(ax1, bx1)
        y1 = max(ay1, by1)
        x2 = min(ax2, bx2)
        y2 = min(ay2, by2)
        iw = max(0.0, x2 - x1)
        ih = max(0.0, y2 - y1)
        inter = iw * ih
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return float(inter / union) if union > 0 else 0.0

    event_track_id = None
    event_person_det = None
    best_iou = 0.0
    try:
        for d in (results if isinstance(results, list) else []):
            if not isinstance(d, dict):
                continue
            if str(d.get("class_name", "")).strip().lower() not in ("person", "kisi", "insan"):
                continue
            bb = d.get("bbox")
            if not bb or len(bb) != 4:
                continue
            iou = _iou_bbox(bb, event_person_bbox)
            if iou > best_iou:
                best_iou = iou
                event_person_det = d
        if isinstance(event_person_det, dict):
            event_track_id = event_person_det.get("track_id")
    except Exception:
        event_track_id = None

    ppe_items = []
    ppe_counts = {"missing": 0, "present": 0}
    face_mask_present = 0
    face_mask_missing = 0
    if event_track_id is not None:
        try:
            etid = int(event_track_id)
        except Exception:
            etid = None
        if etid is not None:
            for d in (results if isinstance(results, list) else []):
                if not isinstance(d, dict):
                    continue
                if not bool(d.get("pose_based", False)):
                    continue
                if str(d.get("class_name", "")).strip().lower() in ("person", "kisi", "insan"):
                    continue
                try:
                    if int(d.get("parent_track_id")) != etid:
                        continue
                except Exception:
                    continue
                ppe_type = str(d.get("ppe_type", "")).strip().lower() or None
                missing = bool(d.get("missing", False))
                if missing:
                    ppe_counts["missing"] += 1
                else:
                    ppe_counts["present"] += 1
                if ppe_type == "face_mask":
                    if missing:
                        face_mask_missing += 1
                    else:
                        face_mask_present += 1
                ppe_items.append(
                    {
                        "ppe_type": ppe_type,
                        "class_name": d.get("class_name"),
                        "missing": missing,
                        "confidence": d.get("confidence"),
                        "bbox": d.get("bbox"),
                        "match_reason": d.get("match_reason"),  # 🎯 Sebebi burada göreceğiz
                    }
                )

    anatomy = None
    keypoints = None
    if isinstance(event_person_det, dict):
        anatomy = event_person_det.get("anatomical_regions")
        kp = event_person_det.get("keypoints")
        keypoints = {"present": kp is not None}

    return {
        "camera_key": camera_key,
        "camera_id": camera_id,
        "company_id": company_id,
        "frame_shape": frame_shape,
        "person_visible": bool(person_visible),
        "person_bbox": event_person_bbox,
        "event_match": {
            "track_id": event_track_id,
            "person_iou_best": best_iou,
            "anatomical_regions": anatomy,
            "keypoints": keypoints,
        },
        "pose_based_ppe_for_person": {
            "counts": ppe_counts,
            "face_mask": {"present": face_mask_present, "missing": face_mask_missing},
            "items": ppe_items,
        },
        "worker": {
            "frame_skip": int(frame_skip),
            "processing_time_ms": processing_time_ms,
        },
        "decision_gate": decision_summary,
        "roi": {"roi_on": roi_on, "roi_stats": roi_stats},
        "temporal_gating": {
            "missing_by_type": temporal_missing_by_type_json,
            "stats_by_type": temporal_stats_by_type,
            "ppe_violations_before": ppe_violations_before,
            "ppe_violations_after": ppe_violations_after,
        },
    }

