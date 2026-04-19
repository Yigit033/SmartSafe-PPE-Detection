"""
DVR/OSD (tarih-saat, kanal yazısı) üzerindeki 'person' false positive azaltma.

`OSD_PERSON_FILTER=1` ile açılır. İsteğe bağlı eşikler:
  OSD_PERSON_MAX_CONF   — hassas bantta bu conf altındaki kişi kutusu elenir (varsayılan 0.52)
  OSD_BOTTOM_Y0         — alt şerit başlangıcı, frame yüksekliği oranı (varsayılan 0.78)
  OSD_SMALL_PERSON_AREA — küçük kutu üst sınırı, frame alanı oranı (varsayılan 0.008)
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


def _fenv(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _osd_filter_enabled(explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return bool(explicit)
    v = os.environ.get("OSD_PERSON_FILTER", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _looks_like_osd_person(
    frame_shape: Tuple[int, ...],
    bbox: List[float],
    confidence: Optional[float] = None,
    keypoint_count: Optional[int] = None,
) -> bool:
    """True => bu kişi kutusu muhtemelen OSD artefaktı, elenmeli."""
    if not frame_shape or len(frame_shape) < 2:
        return False
    fh, fw = int(frame_shape[0]), int(frame_shape[1])
    if fh <= 0 or fw <= 0:
        return False
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return False
    w = max(0.0, x2 - x1)
    h = max(0.0, y2 - y1)
    if w <= 1.0 or h <= 1.0:
        return True
    area = w * h
    frame_area = float(fh * fw)
    area_ratio = area / max(frame_area, 1.0)
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    ar = w / max(h, 1.0)

    bottom_y0 = _fenv("OSD_BOTTOM_Y0", 0.78)
    small_area = _fenv("OSD_SMALL_PERSON_AREA", 0.008)
    max_conf = _fenv("OSD_PERSON_MAX_CONF", 0.52)

    bottom_band = y1 >= fh * bottom_y0
    top_band = y2 <= fh * 0.22
    # Sağ üst / sağ alt OSD (tarih-saat, logo) — dikey olarak geniş aralık
    right_focus = cx >= fw * 0.40 and cy >= fh * 0.62

    # ── Önceki kurallar (dar sağ-alt + üst şerit) ─────────────────────────
    if cx / fw > 0.70 and cy / fh > 0.76 and area_ratio < 0.012:
        if 0.12 <= ar <= 6.0:
            return True
    if y2 / fh <= 0.13 and h / fh <= 0.11 and w / fw >= 0.28:
        return True

    # ── Alt satır zaman damgası: küçük kutu, ekranın alt %22'si ─────────
    if bottom_band and area_ratio <= small_area * 1.5 and cx >= fw * 0.30:
        if 0.06 <= ar <= 10.0:
            return True

    # ── Düşük pose conf + OSD’a yakın bölge (rakam / yazı tipik) ─────────
    sensitive = bottom_band or top_band or (right_focus and cy >= fh * 0.62)
    if sensitive and area_ratio < 0.035:
        if confidence is not None and confidence < max_conf:
            return True
        if keypoint_count is not None and keypoint_count < 9 and area_ratio < 0.012:
            return True

    # ── Çok küçük kutu, sağ yarı + alt bölge (tek tek rakamlar) ───────────
    if area_ratio < 0.002 and cx >= fw * 0.55 and cy >= fh * 0.68:
        return True

    return False


def filter_pose_person_candidates(
    frame_shape: Tuple[int, ...],
    persons: List[Dict[str, Any]],
    enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Pose pipeline içi: kişi adayları listesinden OSD benzeri kutuları çıkar."""
    if not persons or not isinstance(persons, list):
        return persons
    if not _osd_filter_enabled(enabled):
        return persons
    out: List[Dict[str, Any]] = []
    for p in persons:
        if not isinstance(p, dict):
            continue
        bb = p.get("bbox")
        if not isinstance(bb, list) or len(bb) != 4:
            continue
        conf_f: Optional[float] = None
        raw_c = p.get("confidence")
        if raw_c is not None:
            try:
                conf_f = float(raw_c)
            except (TypeError, ValueError):
                conf_f = None
        kpc = len(p.get("keypoints") or [])
        if _looks_like_osd_person(frame_shape, bb, conf_f, keypoint_count=kpc):
            continue
        out.append(p)
    return out


def strip_osd_style_person_detections(
    frame_shape: Tuple[int, ...],
    detections: List[Dict[str, Any]],
    enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    if not detections or not isinstance(detections, list):
        return detections
    if not _osd_filter_enabled(enabled):
        return detections

    out: List[Dict[str, Any]] = []
    for d in detections:
        if not isinstance(d, dict):
            continue
        cn = str(d.get("class_name", "")).strip().lower()
        bb = d.get("bbox")
        if cn in ("person", "kisi", "insan") and isinstance(bb, list) and len(bb) == 4:
            conf_f: Optional[float] = None
            raw_c = d.get("confidence")
            if raw_c is not None:
                try:
                    conf_f = float(raw_c)
                except (TypeError, ValueError):
                    conf_f = None
            if _looks_like_osd_person(frame_shape, bb, conf_f, keypoint_count=None):
                continue
        out.append(d)
    return out
