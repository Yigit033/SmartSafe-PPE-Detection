"""
Person-centric tracking utilities (ByteTrack) for stable track_id assignment.

Used to improve bbox stability and to enable reliability metrics (trackless ratio, jitter).
This is intentionally optional: if `supervision` is not installed, functions become no-ops.

Env:
  - DETECTION_PERSON_TRACKING=1 enables tracking (default: 1)
  - DETECTION_PERSON_TRACK_TTL_SEC prune inactive trackers (default: 30)
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import supervision as sv  # type: ignore
except Exception:
    sv = None  # type: ignore


def person_tracking_enabled() -> bool:
    raw = os.getenv("DETECTION_PERSON_TRACKING", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass
class _TrackerEntry:
    tracker: object
    last_seen: float


_trackers: Dict[str, _TrackerEntry] = {}


def _get_tracker(camera_key: str) -> Optional[object]:
    if sv is None:
        return None
    ent = _trackers.get(camera_key)
    if ent is not None:
        ent.last_seen = time.time()
        return ent.tracker
    try:
        tr = sv.ByteTrack()
        _trackers[camera_key] = _TrackerEntry(tracker=tr, last_seen=time.time())
        return tr
    except Exception as e:
        logger.warning("ByteTrack init failed: %s", e)
        return None


def prune_trackers() -> None:
    """Prune inactive trackers to avoid unbounded memory."""
    ttl = float(os.getenv("DETECTION_PERSON_TRACK_TTL_SEC", "30") or "30")
    cutoff = time.time() - max(5.0, ttl)
    for k in list(_trackers.keys()):
        if _trackers[k].last_seen < cutoff:
            _trackers.pop(k, None)


def assign_track_ids_to_person_detections(
    camera_key: str,
    persons: List[dict],
) -> List[dict]:
    """Attach `track_id` to each person dict in-place when possible.

    Expects each person dict to include:
      - bbox: [x1,y1,x2,y2]
      - confidence: float (optional)
    """
    if not person_tracking_enabled():
        return persons
    if sv is None:
        return persons
    if not persons:
        return persons

    tr = _get_tracker(camera_key)
    if tr is None:
        return persons

    xyxy: List[List[float]] = []
    conf: List[float] = []
    for p in persons:
        bbox = p.get("bbox")
        if not bbox or len(bbox) < 4:
            xyxy.append([0.0, 0.0, 1.0, 1.0])
            conf.append(0.01)
            continue
        try:
            x1, y1, x2, y2 = [float(bbox[i]) for i in range(4)]
        except Exception:
            x1, y1, x2, y2 = 0.0, 0.0, 1.0, 1.0
        xyxy.append([x1, y1, x2, y2])
        try:
            conf.append(float(p.get("confidence", 0.9)))
        except Exception:
            conf.append(0.9)

    det = sv.Detections(
        xyxy=np.asarray(xyxy, dtype=np.float32),
        confidence=np.asarray(conf, dtype=np.float32),
        class_id=np.zeros((len(xyxy),), dtype=np.int64),
    )
    try:
        det2 = tr.update_with_detections(det)  # type: ignore[attr-defined]
        tids = det2.tracker_id
    except Exception as e:
        logger.warning("ByteTrack update failed; disabling for %s: %s", camera_key, e)
        _trackers.pop(camera_key, None)
        return persons

    if tids is None or len(tids) != len(persons):
        return persons

    for i, tid in enumerate(tids):
        if tid is None:
            continue
        # Do not override an existing track_id coming from upstream (e.g. pose model tracker),
        # otherwise pose_based PPE parent_track_id and temporal gating can desync.
        try:
            if persons[i].get("track_id") is not None:
                continue
            persons[i]["track_id"] = int(tid)
        except Exception:
            continue

    prune_trackers()
    return persons

