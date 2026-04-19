#!/usr/bin/env python3
"""
Build Master Food PPE dataset (senior, reproducible).

Why this exists (vs. "quick merge scripts"):
- Name-based class mapping (safer than hardcoding ids)
- Selective extraction per-source (take only the classes you trust)
- Raw data is never mutated (staging is regenerated)
- Generates a manifest for traceability
- Performs sanity checks + optional QC crop-check

Outputs:
  datasets/staging/master_food_ppe_v1/
    images/{train,val,test}/...
    labels/{train,val,test}/...
    data.yaml
    manifest.json
    qc/crops/<class>/...

Usage (PowerShell):
  python tools/datasets/build_master_dataset.py ^
    --config tools/datasets/master_food_ppe_config.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


CANONICAL_SPLITS = ("train", "val", "test")
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return data


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMG_EXTS


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, content: str) -> None:
    _safe_mkdir(path.parent)
    path.write_text(content, encoding="utf-8")


def _try_import_cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except Exception:
        return None


def _try_import_pil():
    try:
        from PIL import Image  # type: ignore

        return Image
    except Exception:
        return None


@dataclass(frozen=True)
class CanonicalContract:
    id_to_name: Dict[int, str]
    name_to_id: Dict[str, int]


def _load_contract(cfg: Dict[str, Any]) -> CanonicalContract:
    canonical_names = cfg.get("canonical_names")
    if not isinstance(canonical_names, dict) or not canonical_names:
        raise ValueError("config.canonical_names must be a non-empty mapping")

    id_to_name: Dict[int, str] = {}
    for k, v in canonical_names.items():
        try:
            idx = int(k)
        except Exception as e:
            raise ValueError(f"canonical_names keys must be int-like: {k}") from e
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"canonical_names[{k}] must be a non-empty string")
        id_to_name[idx] = v.strip().lower()

    name_to_id = {n: i for i, n in id_to_name.items()}
    if len(name_to_id) != len(id_to_name):
        raise ValueError("canonical_names contains duplicate names")
    return CanonicalContract(id_to_name=id_to_name, name_to_id=name_to_id)


def _normalize_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def _build_alias_map(cfg: Dict[str, Any]) -> Dict[str, str]:
    aliases = cfg.get("global_aliases", {}) or {}
    if not isinstance(aliases, dict):
        raise ValueError("config.global_aliases must be a mapping")
    out: Dict[str, str] = {}
    for k, v in aliases.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        out[_normalize_name(k)] = _normalize_name(v)
    return out


def _resolve_canonical(name: str, alias_map: Dict[str, str]) -> str:
    n = _normalize_name(name)
    return alias_map.get(n, n)


def _guess_dataset_root(raw_source_dir: Path) -> Path:
    """
    Roboflow exports commonly create a nested folder like:
      datasets/raw/<name>/<project>-<version>/
    If there's exactly one child directory and it contains data.yaml, use it.
    Otherwise use raw_source_dir itself.
    """
    if (raw_source_dir / "data.yaml").exists():
        return raw_source_dir
    children = [p for p in raw_source_dir.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "data.yaml").exists():
        return children[0]
    # Fallback: search shallow for data.yaml
    for p in children[:10]:
        if (p / "data.yaml").exists():
            return p
    return raw_source_dir


def _load_source_data_yaml(source_root: Path) -> Dict[str, Any]:
    data_yaml = source_root / "data.yaml"
    if not data_yaml.exists():
        raise FileNotFoundError(f"Missing data.yaml in source: {source_root}")
    return _load_yaml(data_yaml)


def _parse_names_map(data_yaml: Dict[str, Any]) -> Dict[int, str]:
    """
    Ultralytics data.yaml 'names' can be list or dict.
    Returns {id: name}.
    """
    names = data_yaml.get("names")
    if isinstance(names, list):
        return {i: str(n) for i, n in enumerate(names)}
    if isinstance(names, dict):
        out: Dict[int, str] = {}
        for k, v in names.items():
            try:
                out[int(k)] = str(v)
            except Exception:
                continue
        return out
    raise ValueError("data.yaml names must be list or dict")


def _discover_split_dirs(source_root: Path, data_yaml: Dict[str, Any]) -> Dict[str, Tuple[Path, Path]]:
    """
    Returns mapping split -> (images_dir, labels_dir).
    Supports common Roboflow YOLOv8 export layout:
      train/images, train/labels
      valid/images, valid/labels  (note: valid == val)
      test/images,  test/labels
    """
    def _split_to_dir(split: str) -> str:
        if split == "val":
            return "valid"
        return split

    out: Dict[str, Tuple[Path, Path]] = {}
    for split in CANONICAL_SPLITS:
        d = _split_to_dir(split)
        img_dir = source_root / d / "images"
        lbl_dir = source_root / d / "labels"
        if img_dir.exists() and lbl_dir.exists():
            out[split] = (img_dir, lbl_dir)

    # Some exports use 'val' folder
    if "val" not in out:
        img_dir = source_root / "val" / "images"
        lbl_dir = source_root / "val" / "labels"
        if img_dir.exists() and lbl_dir.exists():
            out["val"] = (img_dir, lbl_dir)

    # If none found, try flat structure (images/, labels/)
    if not out:
        img_dir = source_root / "images"
        lbl_dir = source_root / "labels"
        if img_dir.exists() and lbl_dir.exists():
            out["train"] = (img_dir, lbl_dir)
    return out


def _iter_images(img_dir: Path) -> Iterable[Path]:
    for p in img_dir.rglob("*"):
        if p.is_file() and _is_image(p):
            yield p


def _read_yolo_label_lines(label_path: Path) -> List[List[str]]:
    if not label_path.exists():
        return []
    lines = _read_text(label_path).splitlines()
    out: List[List[str]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split()
        if len(parts) != 5:
            # Not a strict YOLO box line; skip
            continue
        out.append(parts)
    return out


def _validate_yolo_box(parts: Sequence[str]) -> bool:
    # parts: [cls, x, y, w, h]
    try:
        x, y, w, h = (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
    except Exception:
        return False
    # allow small numerical drift but reject obviously broken
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return False
    if not (0.0 < w <= 1.0 and 0.0 < h <= 1.0):
        return False
    return True


def _remap_label(
    label_path: Path,
    src_id_to_name: Dict[int, str],
    alias_map: Dict[str, str],
    contract: CanonicalContract,
    allowed: Optional[Sequence[str]],
    stats: Dict[str, Any],
) -> List[str]:
    allowed_set = {a.strip().lower() for a in (allowed or []) if str(a).strip()}
    keep_all = not allowed_set

    remapped_lines: List[str] = []
    lines = _read_yolo_label_lines(label_path)
    for parts in lines:
        if not _validate_yolo_box(parts):
            stats["bad_boxes"] = stats.get("bad_boxes", 0) + 1
            continue
        try:
            src_id = int(parts[0])
        except Exception:
            stats["bad_lines"] = stats.get("bad_lines", 0) + 1
            continue

        src_name_raw = src_id_to_name.get(src_id)
        if not src_name_raw:
            continue
        canonical_name = _resolve_canonical(src_name_raw, alias_map)

        if not keep_all and canonical_name not in allowed_set:
            continue

        canonical_id = contract.name_to_id.get(canonical_name)
        if canonical_id is None:
            continue

        parts[0] = str(canonical_id)
        remapped_lines.append(" ".join(parts))
        stats[f"class_{canonical_name}"] = stats.get(f"class_{canonical_name}", 0) + 1

    return remapped_lines


def _choose_split(
    strategy: str,
    split_from_source: str,
    source_name: str,
    rng: random.Random,
    by_source_assignment: Dict[str, str],
    ratios: Tuple[float, float, float],
) -> str:
    strategy = (strategy or "none").strip().lower()
    if strategy == "none":
        return split_from_source
    if strategy == "random":
        r = rng.random()
        train_r, val_r, test_r = ratios
        if r < train_r:
            return "train"
        if r < train_r + val_r:
            return "val"
        return "test"
    if strategy == "by_source":
        # Assign entire source to a split once
        if source_name not in by_source_assignment:
            r = rng.random()
            train_r, val_r, test_r = ratios
            if r < train_r:
                by_source_assignment[source_name] = "train"
            elif r < train_r + val_r:
                by_source_assignment[source_name] = "val"
            else:
                by_source_assignment[source_name] = "test"
        return by_source_assignment[source_name]
    raise ValueError(f"Unknown split.strategy: {strategy}")


def _write_data_yaml(out_dir: Path, contract: CanonicalContract) -> None:
    data = {
        "path": str(out_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": len(contract.id_to_name),
        "names": {i: n for i, n in sorted(contract.id_to_name.items())},
    }
    _write_text(out_dir / "data.yaml", yaml.dump(data, sort_keys=False))


def _save_manifest(out_dir: Path, manifest: Dict[str, Any]) -> None:
    _write_text(out_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))


def _qc_crops(
    out_dir: Path,
    contract: CanonicalContract,
    crops_per_class: int,
    seed: int,
) -> None:
    """
    Generates cropped bbox samples from the *staged* dataset for quick visual audit.
    This is intentionally best-effort: if cv2/PIL isn't installed, it skips silently.
    """
    cv2 = _try_import_cv2()
    Image = _try_import_pil()
    if cv2 is None and Image is None:
        return

    rng = random.Random(seed)
    qc_dir = out_dir / "qc" / "crops"
    _safe_mkdir(qc_dir)

    # Collect candidate (img, label) pairs from train+val only (most useful)
    candidates: List[Tuple[Path, Path]] = []
    for split in ("train", "val"):
        img_dir = out_dir / "images" / split
        lbl_dir = out_dir / "labels" / split
        if not img_dir.exists() or not lbl_dir.exists():
            continue
        for img_path in _iter_images(img_dir):
            lbl_path = lbl_dir / f"{img_path.stem}.txt"
            if lbl_path.exists():
                candidates.append((img_path, lbl_path))

    if not candidates:
        return

    # For each class, sample crops
    for class_id, class_name in contract.id_to_name.items():
        per_class_dir = qc_dir / class_name
        _safe_mkdir(per_class_dir)
        saved = 0

        # Shuffle candidates and scan until enough crops found
        rng.shuffle(candidates)
        for img_path, lbl_path in candidates:
            if saved >= crops_per_class:
                break
            lines = _read_yolo_label_lines(lbl_path)
            if not lines:
                continue
            # Load image once
            img = None
            if cv2 is not None:
                img = cv2.imread(str(img_path))
            elif Image is not None:
                try:
                    img = Image.open(img_path).convert("RGB")
                except Exception:
                    img = None
            if img is None:
                continue

            # Convert to numpy for unified handling
            if cv2 is None and Image is not None:
                import numpy as np  # local import

                img_np = np.array(img)
            else:
                img_np = img

            h, w = img_np.shape[:2]
            for parts in lines:
                if saved >= crops_per_class:
                    break
                try:
                    if int(parts[0]) != class_id:
                        continue
                except Exception:
                    continue
                if not _validate_yolo_box(parts):
                    continue
                x, y, bw, bh = map(float, parts[1:])
                x1 = int((x - bw / 2) * w)
                y1 = int((y - bh / 2) * h)
                x2 = int((x + bw / 2) * w)
                y2 = int((y + bh / 2) * h)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w - 1, x2), min(h - 1, y2)
                if x2 <= x1 or y2 <= y1:
                    continue
                crop = img_np[y1:y2, x1:x2]
                out_path = per_class_dir / f"{img_path.stem}_{saved:04d}.jpg"
                try:
                    if cv2 is not None:
                        cv2.imwrite(str(out_path), crop)
                    else:
                        from PIL import Image as _Image  # type: ignore

                        _Image.fromarray(crop).save(out_path)
                    saved += 1
                except Exception:
                    continue


def build_master(config_path: Path) -> Path:
    cfg = _load_yaml(config_path)
    contract = _load_contract(cfg)
    alias_map = _build_alias_map(cfg)

    sources = cfg.get("sources", [])
    if not isinstance(sources, list) or not sources:
        raise ValueError("config.sources must be a non-empty list")

    out_cfg = cfg.get("output", {}) or {}
    staging_rel = out_cfg.get("staging_dir", "datasets/staging/master_food_ppe_v1")
    out_dir = (REPO_ROOT / str(staging_rel)).resolve()

    # Prepare clean staging structure
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for split in CANONICAL_SPLITS:
        _safe_mkdir(out_dir / "images" / split)
        _safe_mkdir(out_dir / "labels" / split)

    split_cfg = cfg.get("split", {}) or {}
    split_strategy = str(split_cfg.get("strategy", "none"))
    seed = int(split_cfg.get("seed", 1337))
    rng = random.Random(seed)
    train_ratio = float(split_cfg.get("train_ratio", 0.8))
    val_ratio = float(split_cfg.get("val_ratio", 0.2))
    test_ratio = float(split_cfg.get("test_ratio", 0.0))
    ratios = (train_ratio, val_ratio, test_ratio)
    by_source_assignment: Dict[str, str] = {}

    manifest: Dict[str, Any] = {
        "created_at_utc": _utc_now_iso(),
        "config_path": str(config_path),
        "canonical_contract": {i: n for i, n in sorted(contract.id_to_name.items())},
        "split": {
            "strategy": split_strategy,
            "ratios": {"train": train_ratio, "val": val_ratio, "test": test_ratio},
            "seed": seed,
        },
        "sources": [],
        "counts": {"images": {"train": 0, "val": 0, "test": 0}, "labels": {"train": 0, "val": 0, "test": 0}},
        "warnings": [],
    }

    global_stats: Dict[str, Any] = {"bad_boxes": 0, "bad_lines": 0, "kept_images": 0, "skipped_images": 0}
    seen_out_stems: set[str] = set()

    raw_root = REPO_ROOT / "datasets" / "raw"

    for src in sources:
        if not isinstance(src, dict):
            continue
        src_name = str(src.get("name", "")).strip()
        if not src_name:
            continue

        allow = src.get("allow")
        if allow is not None and not isinstance(allow, list):
            raise ValueError(f"source.allow must be a list for {src_name}")

        src_raw_dir = raw_root / src_name
        if not src_raw_dir.exists():
            manifest["warnings"].append(f"Source not found on disk: datasets/raw/{src_name}")
            continue

        src_root = _guess_dataset_root(src_raw_dir)
        data_yaml = _load_source_data_yaml(src_root)
        src_names_map = _parse_names_map(data_yaml)
        split_dirs = _discover_split_dirs(src_root, data_yaml)
        if not split_dirs:
            manifest["warnings"].append(f"No split dirs found under: {src_root}")
            continue

        per_src_stats: Dict[str, Any] = {"name": src_name, "root": str(src_root), "kept_images": 0, "skipped_images": 0}
        per_src_class_counts: Dict[str, int] = {}

        for split_from_source, (img_dir, lbl_dir) in split_dirs.items():
            for img_path in _iter_images(img_dir):
                label_path = lbl_dir / f"{img_path.stem}.txt"
                # Remap labels (may drop all lines)
                remap_stats: Dict[str, Any] = {"bad_boxes": 0, "bad_lines": 0}
                remapped = _remap_label(
                    label_path=label_path,
                    src_id_to_name=src_names_map,
                    alias_map=alias_map,
                    contract=contract,
                    allowed=allow,
                    stats=remap_stats,
                )
                global_stats["bad_boxes"] += remap_stats.get("bad_boxes", 0)
                global_stats["bad_lines"] += remap_stats.get("bad_lines", 0)

                if not remapped:
                    per_src_stats["skipped_images"] += 1
                    global_stats["skipped_images"] += 1
                    continue

                # Choose output split
                out_split = _choose_split(
                    strategy=split_strategy,
                    split_from_source=split_from_source,
                    source_name=src_name,
                    rng=rng,
                    by_source_assignment=by_source_assignment,
                    ratios=ratios,
                )
                if out_split not in CANONICAL_SPLITS:
                    out_split = "train"

                # Unique naming to avoid collisions
                out_stem = f"{src_name}__{img_path.stem}"
                if out_stem in seen_out_stems:
                    # Extremely rare, but keep it deterministic
                    suffix = 2
                    while f"{out_stem}__{suffix}" in seen_out_stems:
                        suffix += 1
                    out_stem = f"{out_stem}__{suffix}"
                seen_out_stems.add(out_stem)

                out_img = out_dir / "images" / out_split / f"{out_stem}{img_path.suffix.lower()}"
                out_lbl = out_dir / "labels" / out_split / f"{out_stem}.txt"
                shutil.copy2(img_path, out_img)
                _write_text(out_lbl, "\n".join(remapped) + "\n")

                per_src_stats["kept_images"] += 1
                global_stats["kept_images"] += 1
                manifest["counts"]["images"][out_split] += 1
                manifest["counts"]["labels"][out_split] += 1

                # Update class counts quickly
                for line in remapped:
                    try:
                        cid = int(line.split()[0])
                    except Exception:
                        continue
                    cname = contract.id_to_name.get(cid, str(cid))
                    per_src_class_counts[cname] = per_src_class_counts.get(cname, 0) + 1

        per_src_stats["class_counts"] = per_src_class_counts
        manifest["sources"].append(per_src_stats)

    _write_data_yaml(out_dir, contract)
    manifest["global_stats"] = global_stats
    _save_manifest(out_dir, manifest)

    qc_cfg = cfg.get("qc", {}) or {}
    crops_per_class = int(qc_cfg.get("crops_per_class", 50))
    _qc_crops(out_dir=out_dir, contract=contract, crops_per_class=crops_per_class, seed=seed)

    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Build master Food PPE dataset into datasets/staging/")
    parser.add_argument(
        "--config",
        type=str,
        default="tools/datasets/master_food_ppe_config.yaml",
        help="Path to build config YAML.",
    )
    args = parser.parse_args()
    out_dir = build_master((REPO_ROOT / args.config).resolve())
    print(f"✅ Master dataset built at: {out_dir}")
    print(f"   - data.yaml: {out_dir / 'data.yaml'}")
    print(f"   - manifest.json: {out_dir / 'manifest.json'}")
    qc_dir = out_dir / "qc" / "crops"
    if qc_dir.exists():
        print(f"   - qc crops: {qc_dir}")


if __name__ == "__main__":
    main()

