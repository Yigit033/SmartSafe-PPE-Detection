"""
Normalize (0–1) analiz poligonunu inference frame piksel koordinatlarına çevirip
tespit listesini ROI dışındaki kutuları elecek şekilde filtreler.

Koordinat uzayı: yeni kayıtlar { "coord_space": "video", "zones": [...] } ile
video çerçevesine göre 0–1 (object-fit: contain ile aynı mantık). Eski düz dizi
formatı da desteklenir (aynı 0–1 çarpımı; eski UI konteyner-normalize ise yeniden
kaydetmek gerekir).
"""

from __future__ import annotations

import json
import os
import logging
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_PERSON_NAMES = frozenset(("person", "kisi", "insan"))


def _is_person_detection(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    cn = str(item.get("class_name", "")).lower().strip()
    return cn in _PERSON_NAMES


def get_roi_contour_pixels(
    frame_shape: Tuple[int, ...], detection_zones_raw: Any
) -> Optional[np.ndarray]:
    """Geçerli ROI yoksa None; aksi halde OpenCV contour Nx1x2 int32."""
    zones = parse_detection_zones(detection_zones_raw)
    norm_poly = _first_polygon_norm(zones)
    if norm_poly is None or len(frame_shape) < 2:
        return None
    h, w = int(frame_shape[0]), int(frame_shape[1])
    return normalized_polygon_to_pixels(norm_poly, w, h)


def build_roi_debug_meta(
    frame_shape: Tuple[int, ...],
    detection_zones_raw: Any,
    results: List[Any],
) -> Optional[Dict[str, Any]]:
    """
    Video akışı overlay / stdout doğrulaması için ROI + kişi içi/dışı meta verisi.

    Dönen dict: polygon (flat [x,y,...]), persons [{bbox, inside}], stats keys
    total_persons, inside_roi, outside_roi — filtre ile aynı kural (alt-orta nokta).
    """
    contour = get_roi_contour_pixels(frame_shape, detection_zones_raw)
    if contour is None:
        return None

    persons_out: List[Dict[str, Any]] = []
    total_persons = 0
    inside_roi = 0
    outside_roi = 0

    for item in results:
        if not _is_person_detection(item):
            continue
        bbox = item.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        try:
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        except (TypeError, ValueError):
            continue
        total_persons += 1
        pt = bbox_bottom_center(bbox)
        if pt is None:
            persons_out.append(
                {
                    "bbox": [x1, y1, x2, y2],
                    "inside": False,
                    "unknown": True,
                }
            )
            continue
        inside = point_inside_polygon(pt, contour)
        if inside:
            inside_roi += 1
        else:
            outside_roi += 1
        persons_out.append(
            {"bbox": [x1, y1, x2, y2], "inside": inside, "unknown": False}
        )

    flat_poly: List[int] = []
    for i in range(contour.shape[0]):
        flat_poly.extend([int(contour[i, 0, 0]), int(contour[i, 0, 1])])

    return {
        "polygon": flat_poly,
        "persons": persons_out,
        "stats": {
            "total_persons": total_persons,
            "inside_roi": inside_roi,
            "outside_roi": outside_roi,
        },
    }


def parse_detection_zones(raw: Any) -> List[List[Dict[str, float]]]:
    """DB'den gelen detection_zones -> poligon listesi (her biri {x,y} 0–1 video uzayı)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        inner = raw.get("zones")
        if isinstance(inner, list):
            return inner
        return []
    if not isinstance(raw, list) or len(raw) == 0:
        return []
    return raw


def _first_polygon_norm(zones: List[Any]) -> Optional[np.ndarray]:
    """İlk poligonu Nx2 float32 (normalize) olarak döndür."""
    if not zones or not isinstance(zones[0], list) or len(zones[0]) < 3:
        return None
    poly = []
    for p in zones[0]:
        if not isinstance(p, dict):
            continue
        try:
            x = float(p.get("x", 0))
            y = float(p.get("y", 0))
        except (TypeError, ValueError):
            continue
        poly.append([x, y])
    if len(poly) < 3:
        return None
    return np.array(poly, dtype=np.float32)


def normalized_polygon_to_pixels(
    norm_poly: np.ndarray, frame_width: int, frame_height: int
) -> np.ndarray:
    """0–1 poligon -> piksel int32 Nx1x2 (OpenCV contour)."""
    w, h = max(1, int(frame_width)), max(1, int(frame_height))
    pts = np.zeros((len(norm_poly), 1, 2), dtype=np.int32)
    for i, (nx, ny) in enumerate(norm_poly):
        pts[i, 0, 0] = int(round(float(nx) * w))
        pts[i, 0, 1] = int(round(float(ny) * h))
    return pts


def bbox_bottom_center(bbox: Any) -> Optional[Tuple[float, float]]:
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    except (TypeError, ValueError):
        return None
    return ((x1 + x2) / 2.0, y2)


def bbox_center(bbox: Any) -> Optional[Tuple[float, float]]:
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    except (TypeError, ValueError):
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def point_inside_polygon(pt: Tuple[float, float], contour: np.ndarray) -> bool:
    r = cv2.pointPolygonTest(contour, pt, False)
    return r >= 0


def intersection_ratio_bbox_roi(
    bbox: Any,
    contour: np.ndarray,
    frame_shape: Tuple[int, ...],
) -> Optional[float]:
    """Return intersection_area(bbox ∩ ROI) / area(bbox) in [0,1].

    Implementation uses a compact raster mask over the bbox region to handle
    arbitrary (possibly concave) polygons robustly.
    """
    if contour is None or len(frame_shape) < 2:
        return None
    if not bbox or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = [int(float(bbox[i])) for i in range(4)]
    except Exception:
        return None

    h, w = int(frame_shape[0]), int(frame_shape[1])
    x1 = max(0, min(x1, w - 1))
    y1 = max(0, min(y1, h - 1))
    x2 = max(x1 + 1, min(x2, w))
    y2 = max(y1 + 1, min(y2, h))

    bw = x2 - x1
    bh = y2 - y1
    area = float(bw * bh)
    if area <= 1.0:
        return None

    # Create a small mask for the bbox region; fill polygon in global coords then crop.
    mask = np.zeros((h, w), dtype=np.uint8)
    try:
        cv2.fillPoly(mask, [contour], 255)
    except Exception:
        return None
    roi_crop = mask[y1:y2, x1:x2]
    if roi_crop.size == 0:
        return None
    inter = float(int(np.count_nonzero(roi_crop)))
    return max(0.0, min(1.0, inter / area))


def roi_score_for_bbox(
    bbox: Any,
    contour: np.ndarray,
    frame_shape: Tuple[int, ...],
    *,
    w_bottom_center: float = 0.65,
    w_intersection: float = 0.35,
) -> Tuple[Optional[float], Optional[bool], Optional[float]]:
    """Score-based ROI decision helpers.

    Returns (roi_score, bottom_center_inside, intersection_ratio).
    - roi_score in [0,1] when computable; None when ROI/bbox invalid.
    """
    pt = bbox_bottom_center(bbox)
    if pt is None:
        return None, None, None
    try:
        inside = bool(point_inside_polygon(pt, contour))
    except Exception:
        inside = None

    inter = intersection_ratio_bbox_roi(bbox, contour, frame_shape)
    if inside is None or inter is None:
        return None, inside, inter
    bc = 1.0 if inside else 0.0
    score = (w_bottom_center * bc) + (w_intersection * float(inter))
    return max(0.0, min(1.0, float(score))), inside, float(inter)


def filter_detections_by_roi(
    frame_shape: Tuple[int, ...],
    detection_zones_raw: Any,
    results: List[Any],
) -> Tuple[List[Any], Dict[str, int], bool]:
    """
    detection_zones boş veya geçersizse results aynen döner.

    Dönen istatistik: total_with_bbox, inside_roi, outside_roi (bbox'lı girdiler için).
    Üçüncü değer: ROI poligonu uygulandı mı.

    Kural:
      - Person/kişi tespitleri → bbox alt-orta noktası ROI içindeyse tutulur.
      - `pose_based=True` PPE tespitleri (ör. "Maske YOK", "Bone") → parent
        person'ın ROI durumunu miras alır (parent_track_id veya parent_bbox
        üzerinden). Parent yoksa veya parent dışarıdaysa bu PPE çizilmez.
      - Diğer tespitler (SH17 ham etiketleri vb.) → eski davranış (alt-orta
        noktası ROI içindeyse tutulur).
    """
    stats = {"total_with_bbox": 0, "inside_roi": 0, "outside_roi": 0}
    zones = parse_detection_zones(detection_zones_raw)
    norm_poly = _first_polygon_norm(zones)
    if norm_poly is None:
        return results, stats, False, None

    logger.info(f"📍 ROI DEBUG | Kamera için kullanılan ham ROI: {detection_zones_raw}")

    if len(frame_shape) < 2:
        return results, stats, False, None
    h, w = int(frame_shape[0]), int(frame_shape[1])
    
    # 🧪 TEST: Eğer poligon sağdan eksikse (UI hatası şüphesi), otomatik olarak en sağa uzat
    # Normalize X değerlerini kontrol et, eğer hiçbiri 0.95'i geçmiyorsa sağa yasla
    if norm_poly is not None and len(norm_poly) > 0:
        max_x = np.max(norm_poly[:, 0])
        _expand_limit = float(os.environ.get('ROI_AUTO_EXPAND_X_THRESHOLD', 0.80))
        if max_x < _expand_limit:
             logger.warning(f"⚠️ ROI sağdan eksik görünüyor (max_x={max_x:.2f}). Otomatik genişletiliyor...")
             # En sağdaki noktaları ve onlara yakın olanları (sağ %20'lik dilim) 1.0'a çek
             threshold = max_x * 0.8
             norm_poly[:, 0] = np.where(norm_poly[:, 0] >= threshold, 1.0, norm_poly[:, 0])

    contour = normalized_polygon_to_pixels(norm_poly, w, h)


    person_inside_by_tid: Dict[int, bool] = {}
    person_inside_by_bbox: List[Tuple[Tuple[int, int, int, int], bool]] = []

    def _eval_inside(bbox: Any) -> Optional[bool]:
        # Ayak ucu yerine merkez noktasına bakıyoruz (daha esnek)
        pt = bbox_center(bbox)
        if pt is None:
            return None
        return bool(point_inside_polygon(pt, contour))

    for item in results:
        if not _is_person_detection(item):
            continue
        bbox = item.get("bbox") if isinstance(item, dict) else None
        if not bbox or len(bbox) < 4:
            continue
        inside = _eval_inside(bbox)
        if inside is not None:
            if not inside:
                logger.debug(f"📍 Person OUTSIDE ROI: bbox={bbox}")
        
        if inside is None:
            continue
        try:
            tid = item.get("track_id") if isinstance(item, dict) else None
            if tid is not None:
                person_inside_by_tid[int(tid)] = inside
        except (TypeError, ValueError):
            pass
        try:
            key = (
                int(bbox[0]),
                int(bbox[1]),
                int(bbox[2]),
                int(bbox[3]),
            )
            person_inside_by_bbox.append((key, inside))
        except (TypeError, ValueError):
            pass

    def _parent_inside(item: Dict[str, Any]) -> Optional[bool]:
        ptid = item.get("parent_track_id")
        if ptid is not None:
            try:
                v = person_inside_by_tid.get(int(ptid))
                if v is not None:
                    return bool(v)
            except (TypeError, ValueError):
                pass
        pbb = item.get("parent_bbox")
        if pbb and len(pbb) == 4:
            try:
                key = (int(pbb[0]), int(pbb[1]), int(pbb[2]), int(pbb[3]))
            except (TypeError, ValueError):
                key = None
            if key is not None:
                for k, v in person_inside_by_bbox:
                    if k == key:
                        return bool(v)
            return _eval_inside(pbb)
        return None

    kept: List[Any] = []
    for item in results:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        bbox = item.get("bbox")
        if not bbox:
            kept.append(item)
            continue
        stats["total_with_bbox"] += 1

        is_pose_based = bool(item.get("pose_based", False))
        inside: Optional[bool]

        if is_pose_based and not _is_person_detection(item):
            inside = _parent_inside(item)
            if inside is None:
                inside = _eval_inside(bbox)
        else:
            inside = _eval_inside(bbox)

        if inside is None:
            kept.append(item)
            continue
        if inside:
            stats["inside_roi"] += 1
            kept.append(item)
        else:
            stats["outside_roi"] += 1

    return kept, stats, True, contour


def _get_empty_return(results, stats):
    return results, stats, False, None
