#!/usr/bin/env python3
"""
Validate a staged YOLO dataset (sanity checks + quick stats).

Checks:
- Missing label/image pairs
- YOLO box numeric validity and range
- Per-class counts (from labels)
- Basic split sizes

Usage:
  python tools/datasets/validate_master_dataset.py --data datasets/staging/master_food_ppe_v1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import yaml


IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
SPLITS = ("train", "val", "test")


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in IMG_EXTS


def _iter_images(dir_path: Path) -> Iterable[Path]:
    if not dir_path.exists():
        return []
    return (p for p in dir_path.rglob("*") if p.is_file() and _is_image(p))


def _read_label_lines(p: Path) -> List[List[str]]:
    if not p.exists():
        return []
    out: List[List[str]] = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split()
        if len(parts) != 5:
            continue
        out.append(parts)
    return out


def _valid(parts: List[str]) -> bool:
    try:
        _ = int(parts[0])
        x, y, w, h = map(float, parts[1:])
    except Exception:
        return False
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return False
    if not (0.0 < w <= 1.0 and 0.0 < h <= 1.0):
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate staged YOLO dataset")
    ap.add_argument("--data", type=str, required=True, help="Staging dataset dir (contains data.yaml)")
    args = ap.parse_args()

    root = Path(args.data).resolve()
    data_yaml = root / "data.yaml"
    if not data_yaml.exists():
        raise SystemExit(f"Missing data.yaml: {data_yaml}")

    cfg = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    names = cfg.get("names", {})
    # names may be dict with int keys or list; normalize to dict[int,str]
    id_to_name: Dict[int, str] = {}
    if isinstance(names, list):
        id_to_name = {i: str(n) for i, n in enumerate(names)}
    elif isinstance(names, dict):
        for k, v in names.items():
            try:
                id_to_name[int(k)] = str(v)
            except Exception:
                continue

    report: Dict[str, object] = {
        "root": str(root),
        "splits": {},
        "class_counts": {},
        "problems": {
            "missing_labels": 0,
            "missing_images": 0,
            "bad_label_lines": 0,
            "bad_boxes": 0,
        },
    }

    class_counts: Dict[str, int] = {}
    probs = report["problems"]  # type: ignore

    for split in SPLITS:
        img_dir = root / "images" / split
        lbl_dir = root / "labels" / split
        split_stats = {"images": 0, "labels": 0}

        # Image -> label existence
        for img in _iter_images(img_dir):
            split_stats["images"] += 1
            lbl = lbl_dir / f"{img.stem}.txt"
            if not lbl.exists():
                probs["missing_labels"] += 1  # type: ignore
                continue
            split_stats["labels"] += 1
            for parts in _read_label_lines(lbl):
                if len(parts) != 5:
                    probs["bad_label_lines"] += 1  # type: ignore
                    continue
                if not _valid(parts):
                    probs["bad_boxes"] += 1  # type: ignore
                    continue
                cid = int(parts[0])
                cname = id_to_name.get(cid, str(cid))
                class_counts[cname] = class_counts.get(cname, 0) + 1

        # Label -> image existence (orphan labels)
        if lbl_dir.exists():
            for lbl in lbl_dir.rglob("*.txt"):
                img_match = None
                for ext in IMG_EXTS:
                    cand = img_dir / f"{lbl.stem}{ext}"
                    if cand.exists():
                        img_match = cand
                        break
                if img_match is None:
                    probs["missing_images"] += 1  # type: ignore

        report["splits"][split] = split_stats  # type: ignore

    report["class_counts"] = dict(sorted(class_counts.items(), key=lambda kv: kv[0]))  # type: ignore

    out = root / "validation_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Wrote: {out}")
    print(json.dumps(report["problems"], indent=2, ensure_ascii=False))
    print("Top class counts:")
    for k, v in list(sorted(class_counts.items(), key=lambda kv: -kv[1]))[:10]:
        print(f"- {k}: {v}")


if __name__ == "__main__":
    main()

