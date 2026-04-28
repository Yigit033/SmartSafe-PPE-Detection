"""
Temporal PPE gating (N-of-M + track-based hysteresis).

Goal: reduce false positives like "Maske eksik" when mask is actually present by
requiring repeated evidence over recent inference frames, per track_id.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, DefaultDict, Dict, List, Set, Tuple


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        v = int(str(raw).strip())
    except Exception:
        return int(default)
    return v


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        v = float(str(raw).strip())
    except Exception:
        return float(default)
    return float(v)


def temporal_gating_enabled() -> bool:
    raw = os.getenv("TEMPORAL_PPE_GATING", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


@dataclass
class _Ev:
    """One evidence sample for a track."""

    t: float
    missing: int  # 0/1
    present: int  # 0/1


_lock = threading.Lock()
_hist: DefaultDict[str, Dict[Tuple[int, str], Deque[_Ev]]] = defaultdict(dict)


def _get_cfg(ppe_type: str) -> Dict[str, object]:
    """
    Per-PPE temporal gating config.

    Global defaults:
      - PPE_N_OF_M_M (default 5)
      - PPE_N_OF_M_N (default 3)
      - PPE_FORGIVE_WINDOW (default 2)
      - PPE_HYSTERESIS_EXTRA (default 1)
      - PPE_TRACK_TTL_S (default 10)

    Backward-compatible mask-specific envs still override for face_mask:
      - MASK_N_OF_M_M / MASK_N_OF_M_N / MASK_FORGIVE_WINDOW / MASK_HYSTERESIS_EXTRA / MASK_TRACK_TTL_S
    """
    ppe_type_n = str(ppe_type or "").strip().lower()

    # Defaults tuned for low-FPS inference (0.8–1.7 FPS) with reasonable latency.
    m = _env_int("PPE_N_OF_M_M", 5)
    n = _env_int("PPE_N_OF_M_N", 3)
    forgive = _env_int("PPE_FORGIVE_WINDOW", 2)
    extra = _env_int("PPE_HYSTERESIS_EXTRA", 1)
    ttl = _env_float("PPE_TRACK_TTL_S", 10.0)

    if ppe_type_n == "face_mask":
        # If project already tuned mask vars, respect them.
        m = _env_int("MASK_N_OF_M_M", 20)
        n = _env_int("MASK_N_OF_M_N", 18)
        forgive = _env_int("MASK_FORGIVE_WINDOW", 8)
        extra = _env_int("MASK_HYSTERESIS_EXTRA", 5)
        ttl = _env_float("MASK_TRACK_TTL_S", ttl)

    if ppe_type_n == "haircap":
        m = _env_int("HAIRCAP_N_OF_M_M", 5)
        n = _env_int("HAIRCAP_N_OF_M_N", 3)
        forgive = _env_int("HAIRCAP_FORGIVE_WINDOW", 3)
        extra = _env_int("HAIRCAP_HYSTERESIS_EXTRA", 2)
        ttl = _env_float("HAIRCAP_TRACK_TTL_S", ttl)

    return {
        "m": max(1, int(m)),
        "n": max(1, int(n)),
        "forgive": max(0, int(forgive)),
        "extra": max(0, int(extra)),
        "ttl": max(1.0, float(ttl)),
    }


def _prune(camera_key: str, now: float, ttl: float) -> None:
    tracks = _hist.get(camera_key)
    if not tracks:
        return
    dead: List[Tuple[int, str]] = []
    for key, q in tracks.items():
        if not q:
            dead.append(key)
            continue
        if now - float(q[-1].t) > ttl:
            dead.append(key)
    for key in dead:
        try:
            del tracks[key]
        except Exception:
            pass


def apply_temporal_ppe_gating(
    camera_key: str,
    detections: List[dict],
) -> Tuple[List[dict], Dict[str, Set[int]], Dict[str, Dict[int, dict]]]:
    """
    Returns (filtered_detections, confirmed_missing_track_ids_by_ppe_type).

    - Operates on pose_based detections that have `ppe_type`.
    - Uses parent_track_id as the identity (must already be assigned for persons).
    - Filters ONLY unconfirmed missing boxes (missing=True). Present boxes are always kept.
    """
    if not temporal_gating_enabled():
        return detections, {}, {}

    now = time.time()

    # Collect evidence per track for this inference step.
    seen_missing: Dict[str, Set[int]] = defaultdict(set)
    seen_present: Dict[str, Set[int]] = defaultdict(set)
    for d in detections:
        if not isinstance(d, dict):
            continue
        if not bool(d.get("pose_based", False)):
            continue
        ppe_type = str(d.get("ppe_type", "")).strip().lower()
        if not ppe_type:
            continue
        ptid = d.get("parent_track_id")
        if ptid is None:
            continue
        try:
            tid = int(ptid)
        except Exception:
            continue
        if bool(d.get("missing", False)):
            seen_missing[ppe_type].add(tid)
        else:
            seen_present[ppe_type].add(tid)

    with _lock:
        tracks = _hist[camera_key]
        # Prune using per-type TTL; compute max TTL to keep pruning cheap.
        ttls = [_get_cfg(ppe).get("ttl", 10.0) for ppe in set(list(seen_missing.keys()) + list(seen_present.keys()))]
        max_ttl = float(max(ttls) if ttls else 10.0)
        _prune(camera_key, now, max_ttl)

        # Update deques for tracks we have evidence for (per ppe_type).
        all_types = set(seen_missing.keys()) | set(seen_present.keys())
        for ppe_type in all_types:
            cfg = _get_cfg(ppe_type)
            m = int(cfg["m"])
            all_seen = set(seen_missing.get(ppe_type, set())) | set(seen_present.get(ppe_type, set()))
            for tid in all_seen:
                k = (int(tid), str(ppe_type))
                q = tracks.get(k)
                if q is None or q.maxlen != m:
                    q = deque(list(q) if q else [], maxlen=m)
                    tracks[k] = q
                q.append(
                    _Ev(
                        t=now,
                        missing=1 if tid in seen_missing.get(ppe_type, set()) else 0,
                        present=1 if tid in seen_present.get(ppe_type, set()) else 0,
                    )
                )

        confirmed_missing: Dict[str, Set[int]] = defaultdict(set)
        stats_by_type: Dict[str, Dict[int, dict]] = defaultdict(dict)
        for (tid, ppe_type), q in tracks.items():
            if not q:
                continue
            cfg = _get_cfg(ppe_type)
            n = int(cfg["n"])
            forgive = int(cfg["forgive"])
            extra = int(cfg["extra"])
            ttl = float(cfg["ttl"])
            m = int(cfg["m"])

            # Ignore stale deques for this type.
            if now - float(q[-1].t) > ttl:
                continue

            miss_cnt = sum(int(ev.missing) for ev in q)
            pres_cnt = sum(int(ev.present) for ev in q)
            if forgive > 0:
                recent = list(q)[-min(forgive, len(q)) :]
                present_recent = any(int(ev.present) == 1 for ev in recent)
            else:
                present_recent = False
            req = n + (extra if present_recent else 0)
            confirmed = bool(miss_cnt >= req)
            if confirmed:
                confirmed_missing[str(ppe_type)].add(int(tid))
            # Capture stats for explainability (% missing over window).
            try:
                wl = int(len(q))
                miss_ratio = float(miss_cnt) / float(wl) if wl > 0 else 0.0
            except Exception:
                wl = None
                miss_ratio = None
            stats_by_type[str(ppe_type)][int(tid)] = {
                "window_len": wl,
                "m": m,
                "n": n,
                "missing_count": int(miss_cnt),
                "present_count": int(pres_cnt),
                "present_recent": bool(present_recent),
                "required_missing": int(req),
                "confirmed_missing": bool(confirmed),
                "missing_ratio": miss_ratio,
                "missing_pct": (miss_ratio * 100.0) if isinstance(miss_ratio, float) else None,
            }

    # Filter out unconfirmed missing mask boxes (keep present boxes).
    out: List[dict] = []
    for d in detections:
        if isinstance(d, dict) and bool(d.get("pose_based", False)) and bool(d.get("missing", False)):
            ppe_type = str(d.get("ppe_type", "")).strip().lower()
            ptid = d.get("parent_track_id")
            try:
                tid = int(ptid) if ptid is not None else None
            except Exception:
                tid = None
            if ppe_type and tid is not None:
                if tid not in confirmed_missing.get(ppe_type, set()):
                    continue
        out.append(d)

    return out, {k: set(v) for k, v in confirmed_missing.items()}, {
        k: dict(v) for k, v in stats_by_type.items()
    }

