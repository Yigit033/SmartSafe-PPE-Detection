"""
Pose tabanlı 'person' adayları için üst seviye kalite kapısı.

YOLO-Pose, DVR OSD (kalın yazı, rakam) üzerinde bazen 'person' skoru üretir;
konum heuristiği tek başına yetmez. Burada iskelet sinyali + kutu boyutu ile
insan dışı örnekleri eliyoruz.

Env:
  PERSON_QUALITY_GATE=1       (varsayılan: açık — OSD_PERSON_FILTER ile uyumlu)
  POSE_MIN_VISIBLE_KEYPOINTS  (varsayılan 10) — COCO 17 içinden bu kadar güçlü nokta
  POSE_MIN_KP_MEAN_CONF       (varsayılan 0.48) — görünür noktaların ortalama conf altındaysa
  POSE_MIN_PERSON_AREA_RATIO  (varsayılan 0.0009) — frame alanına oran; altında 'speckle'
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _gate_enabled() -> bool:
    v = os.environ.get("PERSON_QUALITY_GATE", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _bbox_area_ratio(frame_shape: Tuple[int, ...], bbox: List[float]) -> float:
    if not frame_shape or len(frame_shape) < 2:
        return 0.0
    fh, fw = int(frame_shape[0]), int(frame_shape[1])
    fa = float(max(fh * fw, 1))
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return 0.0
    w = max(0.0, x2 - x1)
    h = max(0.0, y2 - y1)
    return (w * h) / fa


def _mean_keypoint_conf(person: Dict[str, Any]) -> float:
    kps = person.get("keypoints") or []
    if not kps:
        return 0.0
    s = 0.0
    for k in kps:
        try:
            s += float(k.get("confidence", 0.0))
        except (TypeError, ValueError):
            pass
    return s / max(len(kps), 1)


def filter_implausible_pose_persons(
    frame_shape: Tuple[int, ...],
    persons: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    İnsan iskeletine uymayan veya mikroskobik 'person' adaylarını çıkar.
    OSD rakamları genelde: az keypoint, düşük ortalama kp conf, küçük alan.
    """
    if not persons or not isinstance(persons, list):
        return persons
    if not _gate_enabled():
        return persons

    min_kp = _i("POSE_MIN_VISIBLE_KEYPOINTS", 10)
    min_kp_mean = _f("POSE_MIN_KP_MEAN_CONF", 0.48)
    min_area = _f("POSE_MIN_PERSON_AREA_RATIO", 0.0009)

    out: List[Dict[str, Any]] = []
    fh = int(frame_shape[0]) if frame_shape and len(frame_shape) > 0 else 0

    for p in persons:
        if not isinstance(p, dict):
            continue
        bb = p.get("bbox")
        if not isinstance(bb, list) or len(bb) != 4:
            continue
        ar = _bbox_area_ratio(frame_shape, bb)
        if ar < min_area:
            continue

        kps = p.get("keypoints") or []
        nk = len(kps)
        mk = _mean_keypoint_conf(p)

        try:
            y1 = float(bb[1])
        except (TypeError, ValueError):
            y1 = 0.0
        bottom_heavy = fh > 0 and (y1 / fh) >= 0.82

        try:
            box_conf = float(p.get("confidence", 0.0))
        except (TypeError, ValueError):
            box_conf = 0.0

        # Zayıf iskelet + küçük/şüpheli kutu (OSD rakamı tipik profil)
        if nk < min_kp and ar < 0.006:
            continue
        if mk < min_kp_mean and ar < 0.007 and box_conf < 0.72:
            continue
        # Alt OSD bandında, alan 'orta-küçük' + tam iskelet değil + kutu conf tipik OSD
        if bottom_heavy and ar < 0.02 and box_conf < 0.72 and nk < 13:
            continue

        out.append(p)

    return out
