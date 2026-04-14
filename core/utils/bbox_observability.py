"""
BBox observability & reliability metrics.

Goal: make bbox quality measurable and production-debuggable without changing model logic.

Emits periodic INFO summaries per camera_key when enabled via env:
  - DETECTION_BBOX_SUMMARY_SEC (float > 0)

Tracks:
  - trackless_frame_ratio (person detections missing stable track_id)
  - avg_track_lifetime_s (approx; based on last-seen timestamps)
  - bbox_jitter_px (center stddev across a short window per track)
  - invalid_bbox_ratio (x2<=x1 or y2<=y1)
  - clipped_bbox_ratio (bbox touching frame boundaries)
  - roi_flip_rate (inside/outside changes per track; optional)

This module is intentionally lightweight: no external deps beyond stdlib.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, DefaultDict, Dict, Iterable, List, Optional, Tuple


def bbox_summary_interval_sec() -> float:
    raw = os.environ.get("DETECTION_BBOX_SUMMARY_SEC", "0").strip()
    try:
        v = float(raw)
        return v if v > 0 else 0.0
    except ValueError:
        return 0.0


def _center_xy(bbox: Iterable[float]) -> Optional[Tuple[float, float]]:
    try:
        x1, y1, x2, y2 = [float(x) for x in bbox]
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _is_invalid_bbox(bbox: Iterable[float]) -> bool:
    try:
        x1, y1, x2, y2 = [float(x) for x in bbox]
    except Exception:
        return True
    return x2 <= x1 or y2 <= y1


def _is_clipped_bbox(bbox: Iterable[float], frame_w: int, frame_h: int) -> bool:
    try:
        x1, y1, x2, y2 = [float(x) for x in bbox]
    except Exception:
        return False
    if frame_w <= 0 or frame_h <= 0:
        return False
    # Touching borders is a strong signal of clipping.
    eps = 0.5
    return (
        x1 <= eps
        or y1 <= eps
        or x2 >= (frame_w - eps)
        or y2 >= (frame_h - eps)
    )


@dataclass
class _TrackState:
    first_seen: float
    last_seen: float
    centers: Deque[Tuple[float, float]]
    last_inside: Optional[bool] = None
    roi_flips: int = 0


_lock = threading.Lock()

# camera_key -> state
_cam_state: DefaultDict[str, Dict[str, object]] = defaultdict(
    lambda: {
        "last_emit": 0.0,
        "frames": 0,
        "person_frames": 0,
        "trackless_person_frames": 0,
        "invalid_bbox": 0,
        "clipped_bbox": 0,
        "total_person_boxes": 0,
        "tracks": {},  # track_id -> _TrackState
    }
)


def record_bbox_frame(
    logger: logging.Logger,
    camera_key: str,
    *,
    frame_shape: Tuple[int, ...],
    person_detections: List[dict],
    roi_inside_by_track: Optional[Dict[int, bool]] = None,
) -> None:
    """Record one frame worth of bbox signals; emit periodic summary."""
    interval = bbox_summary_interval_sec()
    if interval <= 0:
        return

    now = time.time()
    frame_h = int(frame_shape[0]) if len(frame_shape) > 0 else 0
    frame_w = int(frame_shape[1]) if len(frame_shape) > 1 else 0

    with _lock:
        st = _cam_state[camera_key]
        st["frames"] = int(st["frames"]) + 1

        tracks: Dict[int, _TrackState] = st["tracks"]  # type: ignore[assignment]

        any_person = False
        frame_has_trackless = False

        for pd in person_detections:
            if not isinstance(pd, dict):
                continue
            bbox = pd.get("bbox")
            if not bbox or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                continue
            any_person = True
            st["total_person_boxes"] = int(st["total_person_boxes"]) + 1

            if _is_invalid_bbox(bbox):
                st["invalid_bbox"] = int(st["invalid_bbox"]) + 1
                continue

            if _is_clipped_bbox(bbox, frame_w, frame_h):
                st["clipped_bbox"] = int(st["clipped_bbox"]) + 1

            tid_raw = pd.get("track_id")
            tid: Optional[int] = None
            if tid_raw is not None:
                try:
                    tid = int(tid_raw)
                except Exception:
                    tid = None

            if tid is None:
                frame_has_trackless = True
                continue

            cxy = _center_xy(bbox)
            if cxy is None:
                continue

            ts = tracks.get(tid)
            if ts is None:
                ts = _TrackState(
                    first_seen=now,
                    last_seen=now,
                    centers=deque(maxlen=20),
                )
                tracks[tid] = ts
            ts.last_seen = now
            ts.centers.append(cxy)

            if roi_inside_by_track is not None:
                inside = roi_inside_by_track.get(tid)
                if inside is not None:
                    if ts.last_inside is not None and inside != ts.last_inside:
                        ts.roi_flips += 1
                    ts.last_inside = inside

        if any_person:
            st["person_frames"] = int(st["person_frames"]) + 1
        if frame_has_trackless:
            st["trackless_person_frames"] = int(st["trackless_person_frames"]) + 1

        last_emit = float(st["last_emit"])
        if now - last_emit < interval:
            return
        st["last_emit"] = now

        frames = max(1, int(st["frames"]))
        person_frames = max(1, int(st["person_frames"]))
        trackless_frames = int(st["trackless_person_frames"])
        total_person_boxes = max(1, int(st["total_person_boxes"]))
        invalid_bbox = int(st["invalid_bbox"])
        clipped_bbox = int(st["clipped_bbox"])

        # Track lifetimes and jitter.
        lifetimes: List[float] = []
        jitter_vals: List[float] = []
        roi_flip_rates: List[float] = []

        # Prune stale tracks to bound memory.
        stale_ttl = float(os.environ.get("DETECTION_BBOX_TRACK_TTL_SEC", "10") or "10")
        prune_before = now - max(2.0, stale_ttl)
        for tid in list(tracks.keys()):
            ts = tracks.get(tid)
            if ts is None:
                continue
            if ts.last_seen < prune_before:
                del tracks[tid]
                continue

            lifetimes.append(max(0.0, ts.last_seen - ts.first_seen))
            if len(ts.centers) >= 3:
                xs = [p[0] for p in ts.centers]
                ys = [p[1] for p in ts.centers]
                mx = sum(xs) / len(xs)
                my = sum(ys) / len(ys)
                vx = sum((x - mx) ** 2 for x in xs) / len(xs)
                vy = sum((y - my) ** 2 for y in ys) / len(ys)
                jitter_vals.append(math.sqrt(vx + vy))

            if ts.last_inside is not None and lifetimes:
                # flips per second (approx)
                denom = max(1e-6, ts.last_seen - ts.first_seen)
                roi_flip_rates.append(float(ts.roi_flips) / denom)

        def _avg(v: List[float]) -> float:
            return sum(v) / len(v) if v else 0.0

        def _p95(v: List[float]) -> float:
            if not v:
                return 0.0
            s = sorted(v)
            idx = int(round(0.95 * (len(s) - 1)))
            return float(s[max(0, min(idx, len(s) - 1))])

        trackless_ratio = float(trackless_frames) / float(person_frames)
        invalid_ratio = float(invalid_bbox) / float(total_person_boxes)
        clipped_ratio = float(clipped_bbox) / float(total_person_boxes)

        # Simple health gates (tunable).
        gate_trackless = float(os.environ.get("BBOX_GATE_TRACKLESS_RATIO", "0.20") or "0.20")
        gate_jitter_px = float(os.environ.get("BBOX_GATE_JITTER_PX", "12") or "12")
        avg_jitter = _avg(jitter_vals)

        health = "ok"
        reasons: List[str] = []
        if trackless_ratio > gate_trackless:
            health = "degraded"
            reasons.append(f"trackless>{gate_trackless:.2f}")
        if avg_jitter > gate_jitter_px:
            health = "degraded"
            reasons.append(f"jitter>{gate_jitter_px:.0f}px")
        if invalid_ratio > 0.02:
            health = "degraded"
            reasons.append("invalid_bbox")

        logger.info(
            "📦 BBOX_SUMMARY [%s] health=%s reasons=%s frames=%d person_frames=%d "
            "trackless_frame_ratio=%.3f avg_track_lifetime_s=%.1f "
            "bbox_jitter_px_avg=%.1f bbox_jitter_px_p95=%.1f "
            "invalid_bbox_ratio=%.3f clipped_bbox_ratio=%.3f roi_flip_rate_avg=%.3f "
            "(interval=%.0fs)",
            camera_key,
            health,
            ",".join(reasons) if reasons else "-",
            frames,
            person_frames,
            trackless_ratio,
            _avg(lifetimes),
            avg_jitter,
            _p95(jitter_vals),
            invalid_ratio,
            clipped_ratio,
            _avg(roi_flip_rates),
            interval,
        )

        # Reset counters for next interval but keep track states.
        st["frames"] = 0
        st["person_frames"] = 0
        st["trackless_person_frames"] = 0
        st["invalid_bbox"] = 0
        st["clipped_bbox"] = 0
        st["total_person_boxes"] = 0

