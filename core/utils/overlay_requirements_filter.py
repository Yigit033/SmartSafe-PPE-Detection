"""
Overlay / MJPEG için tespit listesini şirket zorunlu PPE listesine göre süzme.

Ham SH17 + food model çıktısında eldiven, gözlük vb. her sınıf bbox olarak gelir;
UI'da yalnızca `required_ppe` içinde tanımlı olanlar + kişi kutuları gösterilmelidir.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sector.sector_ppe_config import map_sh17_class_to_config_requirement_id


def _norm_class_name(name: str) -> str:
    s = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s


def filter_detections_for_company_required_overlay(
    detections: List[Dict[str, Any]],
    required_ppe: Optional[List[str]],
    sector: Optional[str],
) -> List[Dict[str, Any]]:
    """
    - Kişi (person) kutuları tutulur.
    - PPE / head vb.: model sınıfı → sector_config `id`; `id` required_ppe içindeyse tutulur.
    - required_ppe None veya boş: davranış değişmez (liste olduğu gibi; boş liste = sadece kişi).
    """
    if not detections or not isinstance(detections, list):
        return detections
    if required_ppe is None:
        return detections
    req_set = {str(x).strip().lower() for x in required_ppe if x is not None and str(x).strip()}
    if not req_set:
        out: List[Dict[str, Any]] = []
        for d in detections:
            if not isinstance(d, dict):
                continue
            cn = _norm_class_name(str(d.get("class_name", "")))
            if cn in ("person", "kisi", "insan"):
                out.append(d)
        return out

    out = []
    for d in detections:
        if not isinstance(d, dict):
            continue
        raw_cn = str(d.get("class_name", ""))
        cn = _norm_class_name(raw_cn)
        if cn in ("person", "kisi", "insan"):
            out.append(d)
            continue
        rid = map_sh17_class_to_config_requirement_id(cn, sector)
        if rid and rid in req_set:
            out.append(d)
    return out
