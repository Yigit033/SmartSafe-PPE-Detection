"""
Sektör bazlı PPE tanımları — kaynak: backend/company/sector_config.ts (SECTOR_PPE_CONFIGS).
Bu dosyayı TS tarafı değişince güncelleyin; tek doğruluk kaynağı orasıdır.

Uygulama içi sektör anahtarları (app.py _normalize_sector vb.) resolve_sector_config_key ile
TS anahtarlarına (construction, food, warehouse, maritime, …) eşlenir.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# --- sector_config.ts ile aynı içerik (ppe_requirements[].id + mandatory) -----------------

SECTOR_PPE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "construction": {
        "sector_id": "construction",
        "ppe_requirements": [
            {"id": "helmet", "mandatory": True},
            {"id": "safety_vest", "mandatory": True},
            {"id": "safety_shoes", "mandatory": True},
            {"id": "gloves", "mandatory": False},
        ],
    },
    "manufacturing": {
        "sector_id": "manufacturing",
        "ppe_requirements": [
            {"id": "helmet", "mandatory": True},
            {"id": "safety_vest", "mandatory": True},
            {"id": "gloves", "mandatory": True},
            {"id": "safety_shoes", "mandatory": True},
        ],
    },
    "chemical": {
        "sector_id": "chemical",
        "ppe_requirements": [
            {"id": "gloves", "mandatory": True},
            {"id": "glasses", "mandatory": True},
            {"id": "face_mask", "mandatory": True},
            {"id": "safety_suit", "mandatory": True},
        ],
    },
    "food": {
        "sector_id": "food",
        "ppe_requirements": [
            {"id": "hairnet", "mandatory": True},
            {"id": "face_mask", "mandatory": True},
            {"id": "apron", "mandatory": True},
            {"id": "gloves", "mandatory": False},
        ],
    },
    "warehouse": {
        "sector_id": "warehouse",
        "ppe_requirements": [
            {"id": "vest", "mandatory": True},
            {"id": "shoes", "mandatory": True},
            {"id": "helmet", "mandatory": False},
        ],
    },
    "energy": {
        "sector_id": "energy",
        "ppe_requirements": [
            {"id": "helmet", "mandatory": True},
            {"id": "insulated_gloves", "mandatory": True},
            {"id": "dielectric_boots", "mandatory": True},
            {"id": "safety_vest", "mandatory": True},
        ],
    },
    "petrochemical": {
        "sector_id": "petrochemical",
        "ppe_requirements": [
            {"id": "helmet", "mandatory": True},
            {"id": "gas_mask", "mandatory": True},
            {"id": "safety_suit", "mandatory": True},
            {"id": "gloves", "mandatory": True},
        ],
    },
    "maritime": {
        "sector_id": "maritime",
        "ppe_requirements": [
            {"id": "life_jacket", "mandatory": True},
            {"id": "helmet", "mandatory": True},
            {"id": "shoes", "mandatory": True},
            {"id": "gloves", "mandatory": False},
        ],
    },
    "aviation": {
        "sector_id": "aviation",
        "ppe_requirements": [
            {"id": "headset", "mandatory": True},
            {"id": "safety_vest", "mandatory": True},
            {"id": "shoes", "mandatory": True},
            {"id": "glasses", "mandatory": False},
        ],
    },
}

# Uygulama / DB'den gelen sektör string'leri → sector_config anahtarı
_SECTOR_KEY_ALIASES: Dict[str, str] = {
    "food_beverage": "food",
    "gıda": "food",
    "gida": "food",
    "warehouse_logistics": "warehouse",
    "marine_shipyard": "maritime",
    "marine": "maritime",
    "shipyard": "maritime",
}


def resolve_sector_config_key(sector: Optional[str]) -> str:
    if not sector or not isinstance(sector, str):
        return "construction"
    k = sector.strip().lower()
    return _SECTOR_KEY_ALIASES.get(k, k)


def get_default_mandatory_ppe_ids(sector: Optional[str]) -> List[str]:
    """sector_config.ts'deki mandatory:true olan PPE id'leri (sıra korunur)."""
    key = resolve_sector_config_key(sector)
    cfg = SECTOR_PPE_CONFIGS.get(key) or SECTOR_PPE_CONFIGS["construction"]
    rows = cfg.get("ppe_requirements") or []
    return [r["id"] for r in rows if r.get("mandatory") is True]


def get_all_ppe_ids_for_sector(sector: Optional[str]) -> Set[str]:
    """Sektör şablonunda tanımlı tüm PPE id'leri (zorunlu + opsiyonel)."""
    key = resolve_sector_config_key(sector)
    cfg = SECTOR_PPE_CONFIGS.get(key)
    if not cfg:
        return set()
    rows = cfg.get("ppe_requirements") or []
    return {r["id"] for r in rows if r.get("id")}


# SH17 / iç model sınıf adı → sector_config `id` (uyumluluk analizi için)
# Gıda: model tarafı haircap / safety_suit kullanır; TS id'leri hairnet / apron.
_SECTOR_SH17_TO_CONFIG_ID: Dict[str, Dict[str, str]] = {
    "food": {
        "haircap": "hairnet",
        "head": "hairnet",
        "hairnet": "hairnet",
        "hair_net": "hairnet",
        "face_mask_medical": "face_mask",
        "face_mask": "face_mask",
        "medical_suit": "apron",
        "safety_suit": "apron",
        "apron": "apron",
        "gloves": "gloves",
    },
    "construction": {
        "helmet": "helmet",
        "safety_vest": "safety_vest",
        "shoes": "safety_shoes",
        "safety_shoes": "safety_shoes",
        "gloves": "gloves",
    },
    "warehouse": {
        "safety_vest": "vest",
        "vest": "vest",
        "shoes": "shoes",
        "helmet": "helmet",
    },
    "chemical": {
        "face_mask_medical": "face_mask",
        "face_mask": "face_mask",
        "gloves": "gloves",
        "glasses": "glasses",
        "safety_suit": "safety_suit",
        "medical_suit": "safety_suit",
    },
    "manufacturing": {
        "helmet": "helmet",
        "safety_vest": "safety_vest",
        "gloves": "gloves",
        "shoes": "safety_shoes",
        "glasses": "glasses",
    },
}


def map_sh17_class_to_config_requirement_id(
    class_name: Optional[str], sector: Optional[str]
) -> Optional[str]:
    """
    Model çıktısı (SH17 canonical / fine-tune isimleri) → sector_config.ts `id`.
    Eşleşme yoksa None.
    """
    if not class_name or not isinstance(class_name, str):
        return None
    cn = class_name.strip().lower()
    sk = resolve_sector_config_key(sector)
    allowed = get_all_ppe_ids_for_sector(sk)
    if cn in allowed:
        return cn
    per = _SECTOR_SH17_TO_CONFIG_ID.get(sk, {})
    return per.get(cn)


def sector_default_ppe_map() -> Dict[str, List[str]]:
    """
    app.py vb. için: normalize edilmiş sektör anahtarı → varsayılan zorunlu PPE id listesi.
    Eski SECTOR_DEFAULT_PPE anahtarları + TS sektör anahtarları.
    """
    m: Dict[str, List[str]] = {}
    for ts_key in SECTOR_PPE_CONFIGS:
        m[ts_key] = get_default_mandatory_ppe_ids(ts_key)
    # Uygulama alias'ları
    m["food_beverage"] = m["food"]
    m["warehouse_logistics"] = m["warehouse"]
    m["marine_shipyard"] = m["maritime"]
    return m
