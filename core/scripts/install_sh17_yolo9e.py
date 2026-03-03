#!/usr/bin/env python3
"""
Helper script to install a single SH17 YOLOv9-e weight file
into all expected SmartSafe SH17 model paths.

Usage:
1) Download yolo9e.pt from:
   https://github.com/ahmadmughees/SH17dataset/releases/download/v1/yolo9e.pt
2) Save it as: models/yolo9e.pt  (project root)
3) Run:
   venv\Scripts\python scripts/install_sh17_yolo9e.py
"""

import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
SOURCE_WEIGHT = MODELS_DIR / "yolo9e.pt"


TARGETS = {
    "base": MODELS_DIR / "sh17_base" / "sh17_base_model" / "weights" / "best.pt",
    "construction": MODELS_DIR / "sh17_construction" / "sh17_construction_model" / "weights" / "best.pt",
    "manufacturing": MODELS_DIR / "sh17_manufacturing" / "sh17_manufacturing_model" / "weights" / "best.pt",
    "chemical": MODELS_DIR / "sh17_chemical" / "sh17_chemical_model" / "weights" / "best.pt",
    "food_beverage": MODELS_DIR / "sh17_food_beverage" / "sh17_food_beverage_model" / "weights" / "best.pt",
    "warehouse_logistics": MODELS_DIR / "sh17_warehouse_logistics" / "sh17_warehouse_logistics_model" / "weights" / "best.pt",
    "energy": MODELS_DIR / "sh17_energy" / "sh17_energy_model" / "weights" / "best.pt",
    "petrochemical": MODELS_DIR / "sh17_petrochemical" / "sh17_petrochemical_model" / "weights" / "best.pt",
    "marine_shipyard": MODELS_DIR / "sh17_marine_shipyard" / "sh17_marine_shipyard_model" / "weights" / "best.pt",
    "aviation": MODELS_DIR / "sh17_aviation" / "sh17_aviation_model" / "weights" / "best.pt",
}


def main() -> None:
    # Avoid emojis in console output to prevent Windows encoding issues
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Looking for source weight: {SOURCE_WEIGHT}")

    if not SOURCE_WEIGHT.exists():
        print("Source weight file not found.")
        print("Please download yolo9e.pt and place it at:")
        print(f"  {SOURCE_WEIGHT}")
        return

    for sector, target in TARGETS.items():
        target_dir = target.parent
        os.makedirs(target_dir, exist_ok=True)

        print(f"Installing for sector '{sector}':")
        print(f"  {SOURCE_WEIGHT}  ->  {target}")
        shutil.copy2(SOURCE_WEIGHT, target)

    print("\nAll SH17 sector paths now have best.pt = yolo9e.pt")
    print("You can now start the backend or offline test;")
    print("SH17ModelManager will load these weights for all sectors.")


if __name__ == "__main__":
    main()

