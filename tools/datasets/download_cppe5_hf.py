#!/usr/bin/env python3
"""
Download CPPE-5 from Hugging Face and materialize a YOLO layout compatible with
`tools/datasets/build_master_dataset.py` (train|test/images + labels, data.yaml).

Canonical HF dataset (paper / HF dataset card):
  https://huggingface.co/datasets/xuan-yuan/cppe-5

Why not Roboflow mirrors:
  Universe mirrors can disappear; HF repo_id + revision is the reproducible anchor.

Dependencies (use a small venv if you also pin `transformers` against `huggingface_hub`):
  python -m pip install -r tools/datasets/requirements_hf.txt

Usage:
  python tools/datasets/download_cppe5_hf.py --clean
  python tools/datasets/download_cppe5_hf.py --repo-id xuan-yuan/cppe-5 --revision main --clean
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = REPO_ROOT / "datasets" / "raw"

# CPPE-5 (HF) category ids -> names must match build_master name-based remap + allow lists.
CPPE5_CLASS_NAMES: Tuple[str, ...] = (
    "coverall",
    "face_shield",
    "gloves",
    "goggles",
    "mask",
)


def _parse_dotenv_line(line: str) -> Optional[tuple[str, str]]:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if "=" not in s:
        return None
    key, val = s.split("=", 1)
    key = key.strip()
    val = val.strip().strip("'").strip('"')
    if not key:
        return None
    return key, val


def _bootstrap_hf_env() -> None:
    """Load HF_TOKEN / HUGGING_FACE_HUB_TOKEN from core/.env or repo .env if unset."""
    for rel in ("core/.env", ".env"):
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parsed = _parse_dotenv_line(raw)
            if not parsed:
                continue
            k, v = parsed
            if k in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN") and v and not os.environ.get(k):
                os.environ[k] = v
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if tok and not os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        os.environ["HUGGING_FACE_HUB_TOKEN"] = tok


def _iter_pairs(objects: Any) -> Iterable[Tuple[int, Sequence[float]]]:
    """
    HF CPPE-5 uses a dict-of-columns:
      {'bbox': [[x,y,w,h], ...], 'category': [..], ...}
    """
    if not isinstance(objects, dict):
        return
    cats = objects.get("category") or []
    bbs = objects.get("bbox") or []
    if not isinstance(cats, (list, tuple)) or not isinstance(bbs, (list, tuple)):
        return
    n = min(len(cats), len(bbs))
    for i in range(n):
        yield int(cats[i]), bbs[i]


def _coco_xywh_to_yolo_line(cls_id: int, xywh: Sequence[float], iw: int, ih: int) -> Optional[str]:
    try:
        x, y, bw, bh = (float(xywh[0]), float(xywh[1]), float(xywh[2]), float(xywh[3]))
    except Exception:
        return None
    if iw <= 0 or ih <= 0:
        return None
    xmin = max(0.0, min(float(iw), x))
    ymin = max(0.0, min(float(ih), y))
    xmax = max(0.0, min(float(iw), x + bw))
    ymax = max(0.0, min(float(ih), y + bh))
    bw2 = xmax - xmin
    bh2 = ymax - ymin
    if bw2 <= 1.0 or bh2 <= 1.0:
        return None
    xc = (xmin + bw2 / 2.0) / float(iw)
    yc = (ymin + bh2 / 2.0) / float(ih)
    wn = bw2 / float(iw)
    hn = bh2 / float(ih)
    if not (0.0 <= xc <= 1.0 and 0.0 <= yc <= 1.0):
        return None
    if not (0.0 < wn <= 1.0 and 0.0 < hn <= 1.0):
        return None
    if cls_id < 0 or cls_id >= len(CPPE5_CLASS_NAMES):
        return None
    return f"{cls_id} {xc:.6f} {yc:.6f} {wn:.6f} {hn:.6f}"


def _count_images(dir_path: Path) -> int:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if not dir_path.exists():
        return 0
    return sum(1 for p in dir_path.rglob("*") if p.is_file() and p.suffix.lower() in exts)


def _count_labels(dir_path: Path) -> int:
    if not dir_path.exists():
        return 0
    return sum(1 for p in dir_path.rglob("*.txt") if p.is_file())


def _verify_export(out_dir: Path) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"root": str(out_dir)}
    for split in ("train", "test"):
        img_dir = out_dir / split / "images"
        lbl_dir = out_dir / split / "labels"
        stats[f"{split}_images"] = _count_images(img_dir)
        stats[f"{split}_labels"] = _count_labels(lbl_dir)
    if not (out_dir / "data.yaml").exists():
        raise RuntimeError(f"Missing data.yaml under {out_dir}")
    if stats["train_images"] == 0:
        raise RuntimeError(f"No train images after export: {stats}")
    return stats


def _write_data_yaml(out_dir: Path, *, repo_id: str) -> None:
    payload = {
        "path": ".",
        "train": "train/images",
        "test": "test/images",
        "names": list(CPPE5_CLASS_NAMES),
        "nc": len(CPPE5_CLASS_NAMES),
        "hf": {
            "dataset": str(repo_id),
            "note": "CPPE-5 from Hugging Face; YOLO layout generated locally for build_master_dataset.py.",
        },
    }
    (out_dir / "data.yaml").write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download CPPE-5 from Hugging Face into datasets/raw/<name>/")
    parser.add_argument("--name", default="cppe5_hf", help="Folder name under datasets/raw/")
    parser.add_argument("--repo-id", default="xuan-yuan/cppe-5", help="Hugging Face datasets repo id")
    parser.add_argument("--revision", default=None, help="Optional HF git revision (branch/tag/commit)")
    parser.add_argument("--clean", action="store_true", help="Delete output directory before writing")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Debug: cap rows per split (writes fewer images than full dataset)",
    )
    args = parser.parse_args()

    _bootstrap_hf_env()

    try:
        from datasets import load_dataset  # type: ignore
        from tqdm import tqdm  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "Missing dependency. Install with:\n"
            "  python -m pip install -r tools/datasets/requirements_hf.txt\n"
            f"Original import error: {e}"
        ) from e

    out_dir = (RAW_ROOT / str(args.name)).resolve()
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)

    (out_dir / "train" / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "train" / "labels").mkdir(parents=True, exist_ok=True)
    (out_dir / "test" / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "test" / "labels").mkdir(parents=True, exist_ok=True)

    load_kw: Dict[str, Any] = {}
    if args.revision:
        load_kw["revision"] = args.revision

    ds = load_dataset(str(args.repo_id), **load_kw)

    manifest: Dict[str, Any] = {
        "repo_id": str(args.repo_id),
        "revision": args.revision,
        "class_names": list(CPPE5_CLASS_NAMES),
        "rows": {},
    }

    for split in ("train", "test"):
        split_ds = ds[split]
        n = len(split_ds)
        limit = n if args.max_rows is None else min(int(args.max_rows), n)
        rows_out: List[Dict[str, Any]] = []

        for i in tqdm(range(limit), desc=f"cppe5_hf:{split}"):
            ex = split_ds[i]
            image_id = ex.get("image_id", i)
            stem = f"{split}_{int(image_id)}"

            img = ex["image"]
            iw = int(ex.get("width") or 0)
            ih = int(ex.get("height") or 0)
            if hasattr(img, "size"):
                pw, ph = img.size
                if iw <= 0:
                    iw = int(pw)
                if ih <= 0:
                    ih = int(ph)

            img_path = out_dir / split / "images" / f"{stem}.jpg"
            if hasattr(img, "convert"):
                img.convert("RGB").save(img_path, format="JPEG", quality=95)
            else:
                raise RuntimeError("Unexpected image object type; expected PIL.Image")

            lines: List[str] = []
            for cls_id, bb in _iter_pairs(ex.get("objects")):
                ln = _coco_xywh_to_yolo_line(cls_id, bb, iw, ih)
                if ln:
                    lines.append(ln)

            lbl_path = out_dir / split / "labels" / f"{stem}.txt"
            lbl_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

            rows_out.append({"stem": stem, "split": split, "hf_image_id": image_id, "width": iw, "height": ih, "n_boxes": len(lines)})

        manifest["rows"][split] = rows_out

    _write_data_yaml(out_dir, repo_id=str(args.repo_id))

    (out_dir / "hf_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    stats = _verify_export(out_dir)
    print(f"OK CPPE-5 HF export ready: {out_dir}")
    print(f"   verify: {stats}")


if __name__ == "__main__":
    main()
