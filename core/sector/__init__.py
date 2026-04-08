"""Sektör / PPE yapılandırması — `backend/company/sector_config.ts` ile senkron tutulmalı."""

from .sector_ppe_config import (
    get_all_ppe_ids_for_sector,
    get_default_mandatory_ppe_ids,
    map_sh17_class_to_config_requirement_id,
    resolve_sector_config_key,
    sector_default_ppe_map,
)

__all__ = [
    "get_all_ppe_ids_for_sector",
    "get_default_mandatory_ppe_ids",
    "map_sh17_class_to_config_requirement_id",
    "resolve_sector_config_key",
    "sector_default_ppe_map",
]
