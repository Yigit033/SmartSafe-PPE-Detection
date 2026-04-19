"""Runtime decision engine for bbox reliability.

Turns signals (ROI score, tracking quality, stability) into runtime behavior:
ACCEPT / UNCERTAIN / REJECT.

When non-ACCEPT: caller should suppress violation events (avoid false alerts).
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, DefaultDict, Dict, List, Optional, Tuple


DecisionState = str  # "ACCEPT" | "UNCERTAIN" | "REJECT"


def decision_engine_enabled() -> bool:
    raw = os.getenv("DETECTION_DECISION_ENGINE", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else float(x)


def _iou(a: List[float], b: List[float]) -> float:
    try:
        ax1, ay1, ax2, ay2 = [float(v) for v in a]
        bx1, by1, bx2, by2 = [float(v) for v in b]
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


def _center(b: List[float]) -> Optional[Tuple[float, float]]:
    if not b or len(b) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in b]
    except Exception:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


@dataclass
class _TState:
    first_seen: float
    last_seen: float
    last_bbox: List[float]
    centers: Deque[Tuple[float, float]]
    last_iou: float = 1.0


_lock = threading.Lock()
_state: DefaultDict[str, Dict[int, _TState]] = defaultdict(dict)


def _track_quality(ts: _TState) -> Tuple[float, float, float]:
    """Return (track_conf, stability_score, jitter_px)."""
    lifetime = max(0.0, ts.last_seen - ts.first_seen)
    lifetime_scale = float(os.getenv("TRACK_CONF_LIFETIME_S", "1.0") or "1.0")
    # Warmup floor: a brand-new track shouldn't force immediate REJECT.
    lifetime_score = _clip01(lifetime / max(0.25, lifetime_scale))
    lifetime_floor = float(os.getenv("TRACK_CONF_WARMUP_FLOOR", "0.35") or "0.35")
    if lifetime_score < lifetime_floor:
        lifetime_score = float(lifetime_floor)

    jitter_px = 0.0
    if len(ts.centers) >= 3:
        xs = [p[0] for p in ts.centers]
        ys = [p[1] for p in ts.centers]
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        vx = sum((x - mx) ** 2 for x in xs) / len(xs)
        vy = sum((y - my) ** 2 for y in ys) / len(ys)
        jitter_px = math.sqrt(vx + vy)

    # Convert jitter to [0,1] where lower jitter => higher score.
    jitter_scale = float(os.getenv("TRACK_CONF_JITTER_SCALE_PX", "20") or "20")
    jitter_score = math.exp(-float(jitter_px) / max(1.0, jitter_scale))

    # Stability from IoU continuity (already clipped by EMA reset logic elsewhere).
    stability_score = _clip01(float(ts.last_iou))

    track_conf = _clip01(lifetime_score * jitter_score)
    return track_conf, stability_score, float(jitter_px)


def decide_frame(
    camera_key: str,
    *,
    persons: List[dict],
    frame_shape: Tuple[int, ...],
    contour: object | None = None,
    roi_score_fn=None,
) -> Dict[str, object]:
    """Mutates `persons` by attaching decision fields.

    Returns frame-level decision summary:
      {state, reasons, people_accept, people_uncertain, people_reject}
    """
    if not decision_engine_enabled():
        return {"state": "ACCEPT", "reasons": [], "people_accept": len(persons), "people_uncertain": 0, "people_reject": 0}

    now = time.time()
    accept = 0
    uncertain = 0
    reject = 0

    roi_reject_t = float(os.getenv("ROI_REJECT_T", "0.20") or "0.20")
    roi_uncertain_t = float(os.getenv("ROI_UNCERTAIN_T", "0.50") or "0.50")

    conf_reject_t = float(os.getenv("FINAL_CONF_REJECT_T", "0.20") or "0.20")
    conf_uncertain_t = float(os.getenv("FINAL_CONF_UNCERTAIN_T", "0.35") or "0.35")

    reasons: List[str] = []

    with _lock:
        tracks = _state[camera_key]

        for p in persons:
            if not isinstance(p, dict):
                continue
            bbox = p.get("bbox")
            if not bbox or len(bbox) < 4:
                p["decision"] = "REJECT"
                p["decision_reason"] = "missing_bbox"
                reject += 1
                continue

            try:
                bb = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            except Exception:
                p["decision"] = "REJECT"
                p["decision_reason"] = "bbox_parse"
                reject += 1
                continue

            tid = p.get("track_id")
            tid_i: Optional[int] = None
            if tid is not None:
                try:
                    tid_i = int(tid)
                except Exception:
                    tid_i = None

            model_conf = 0.9
            try:
                model_conf = float(p.get("confidence", 0.9))
            except Exception:
                model_conf = 0.9
            model_conf = _clip01(model_conf)

            roi_score = 1.0
            roi_state: DecisionState = "ACCEPT"
            if contour is not None and roi_score_fn is not None:
                try:
                    s, _inside, _inter = roi_score_fn(bb, contour, frame_shape)
                    if s is not None:
                        roi_score = _clip01(float(s))
                except Exception:
                    pass
                if roi_score < roi_reject_t:
                    roi_state = "REJECT"
                elif roi_score < roi_uncertain_t:
                    roi_state = "UNCERTAIN"

            track_conf = 0.6 if tid_i is not None else 0.40 # 0.15'ten 0.40'a çıkarıldı (takip olmasa da hemen reddetme)
            stability_score = 0.6
            jitter_px = 0.0

            if tid_i is not None:
                ts = tracks.get(tid_i)
                cxy = _center(bb)
                if ts is None:
                    ts = _TState(first_seen=now, last_seen=now, last_bbox=bb, centers=deque(maxlen=20))
                    tracks[tid_i] = ts
                else:
                    ts.last_iou = _iou(ts.last_bbox, bb)
                    ts.last_bbox = bb
                    ts.last_seen = now
                if cxy is not None:
                    ts.centers.append(cxy)
                track_conf, stability_score, jitter_px = _track_quality(ts)

            final_conf = _clip01(model_conf * float(track_conf) * float(roi_score) * float(stability_score))

            # Decision is driven by the weakest link first (ROI hard reject), then confidence fusion.
            if roi_state == "REJECT":
                state: DecisionState = "REJECT"
                reason = "roi_reject"
            elif final_conf < conf_reject_t:
                state = "REJECT"
                reason = "final_conf_reject"
            elif roi_state == "UNCERTAIN" or final_conf < conf_uncertain_t:
                state = "UNCERTAIN"
                reason = "uncertain"
            else:
                state = "ACCEPT"
                reason = "ok"

            p["roi_score"] = float(roi_score)
            p["track_conf"] = float(track_conf)
            p["stability_score"] = float(stability_score)
            p["jitter_px"] = float(jitter_px)
            p["final_conf"] = float(final_conf)
            p["decision"] = state
            p["decision_reason"] = reason

            if state == "ACCEPT":
                accept += 1
            elif state == "UNCERTAIN":
                uncertain += 1
            else:
                reject += 1

    frame_state: DecisionState
    if accept > 0:
        frame_state = "ACCEPT"
    elif uncertain > 0:
        frame_state = "UNCERTAIN"
    else:
        frame_state = "REJECT"

    if frame_state != "ACCEPT":
        reasons.append("decision_engine")

    return {
        "state": frame_state,
        "reasons": reasons,
        "people_accept": accept,
        "people_uncertain": uncertain,
        "people_reject": reject,
    }

