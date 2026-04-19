#!/usr/bin/env python3
"""
Roboflow dataset downloader (reproducible, repo-friendly).

Design goals:
- No hardcoded API keys (use env var ROBOFLOW_API_KEY)
- All downloads go under: datasets/raw/<name>/
- Uses a single registry file: tools/datasets/dataset_sources.yaml

Usage (PowerShell):
  $env:ROBOFLOW_API_KEY="..."
  python tools/datasets/download_roboflow.py --list
  python tools/datasets/download_roboflow.py --name ppe_food_manufacturing_v5
  python tools/datasets/download_roboflow.py --name ppe_food_manufacturing_v5 --clean
  python tools/datasets/download_roboflow.py --all

Notes:
- This script uses the official `roboflow` Python SDK if installed.
  If missing, install it:
    pip install roboflow
- Roboflow SDK quirk: `Version.download(..., overwrite=False)` will **skip** downloading if the
  target `location` directory already exists — even if it's empty. This script avoids pre-creating
  that directory and defaults to `overwrite=True` unless you pass `--no-overwrite`.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_YAML = REPO_ROOT / "tools" / "datasets" / "dataset_sources.yaml"
RAW_DIR = REPO_ROOT / "datasets" / "raw"


def _has_roboflow_data_file(dir_path: Path) -> bool:
    return (dir_path / "data.yaml").exists() or (dir_path / "data.yml").exists()


def _guess_yolo_dataset_root(base_dir: Path) -> Path:
    """
    Roboflow exports often nest like:
      <out_dir>/<Project>-<version>/data.yaml
    """
    if _has_roboflow_data_file(base_dir):
        return base_dir
    children = [p for p in base_dir.iterdir() if p.is_dir()]
    if len(children) == 1 and _has_roboflow_data_file(children[0]):
        return children[0]
    for p in children[:20]:
        if _has_roboflow_data_file(p):
            return p
    return base_dir


def _find_data_yaml_root(search_root: Path, *, max_depth: int = 6) -> Optional[Path]:
    """
    Breadth-first search for `data.yaml` / `data.yml` under search_root (bounded depth).
    Returns the directory containing the dataset yaml (not the file path).
    """
    if not search_root.exists():
        return None

    queue: List[tuple[Path, int]] = [(search_root, 0)]
    seen: set[str] = set()
    candidates: List[Path] = []

    while queue:
        node, depth = queue.pop(0)
        key = str(node.resolve())
        if key in seen:
            continue
        seen.add(key)

        if (node / "data.yaml").exists() or (node / "data.yml").exists():
            candidates.append(node)

        if depth >= max_depth:
            continue

        try:
            for child in node.iterdir():
                if child.is_dir():
                    queue.append((child, depth + 1))
        except Exception:
            continue

    if not candidates:
        return None

    def _score(p: Path) -> tuple[int, int, str]:
        # Prefer roots that look like YOLO exports (have train/images)
        train_img = p / "train" / "images"
        score = 0
        if train_img.exists():
            score -= 10_000
        # Prefer shallower paths, then lexicographic stability
        return (score, len(p.parts), str(p))

    candidates.sort(key=_score)
    return candidates[0]


def _debug_list_dir(path: Path, *, limit: int = 40) -> str:
    if not path.exists():
        return f"(missing) {path}"
    try:
        names = [p.name for p in path.iterdir()]
    except Exception as e:
        return f"(unreadable) {path}: {e}"
    names.sort()
    if len(names) > limit:
        head = ", ".join(names[:limit])
        return f"{path} contains {len(names)} entries (showing {limit}): {head}, ..."
    return f"{path} contains {len(names)} entries: {', '.join(names)}"



def _count_images(dir_path: Path) -> int:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if not dir_path.exists():
        return 0
    n = 0
    for p in dir_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            n += 1
    return n


def _count_labels(dir_path: Path) -> int:
    if not dir_path.exists():
        return 0
    return sum(1 for p in dir_path.rglob("*.txt") if p.is_file())


def _verify_yolo_export(dataset_root: Path) -> Dict[str, Any]:
    """
    Basic sanity checks for a YOLO-style Roboflow export.
    """
    if not _has_roboflow_data_file(dataset_root):
        raise RuntimeError(f"Download verification failed: missing data.yaml/data.yml under: {dataset_root}")

    # Common layouts (Roboflow YOLO exports vary slightly)
    train_img_candidates = [
        dataset_root / "train" / "images",
        dataset_root / "images" / "train",
    ]
    train_lbl_candidates = [
        dataset_root / "train" / "labels",
        dataset_root / "labels" / "train",
    ]
    val_img_candidates = [
        dataset_root / "valid" / "images",
        dataset_root / "val" / "images",
        dataset_root / "images" / "valid",
        dataset_root / "images" / "val",
    ]

    train_img = next((p for p in train_img_candidates if p.exists()), train_img_candidates[0])
    train_lbl = next((p for p in train_lbl_candidates if p.exists()), train_lbl_candidates[0])

    stats = {
        "dataset_root": str(dataset_root),
        "train_images": _count_images(train_img),
        "train_labels": _count_labels(train_lbl),
        "valid_images": max((_count_images(p) for p in val_img_candidates if p.exists()), default=0),
        "val_images": max((_count_images(p) for p in val_img_candidates if p.exists()), default=0),
    }

    if stats["train_images"] == 0:
        raise RuntimeError(
            "Download verification failed: no training images found.\n"
            f"Tried train image dirs: {[str(p) for p in train_img_candidates]}\n"
            f"Got stats: {stats}\n"
            f"{_debug_list_dir(dataset_root)}"
        )

    return stats


def _parse_dotenv_line(line: str) -> Optional[tuple[str, str]]:
    """
    Minimal .env parser (good enough for KEY=VALUE lines).
    - Ignores blank lines and comments (# ...)
    - Strips optional surrounding quotes on values
    """
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


def _load_env_file(path: Path, *, override: bool = False) -> int:
    """
    Load KEY=VALUE pairs into os.environ.
    Returns number of keys set.
    """
    if not path.exists():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = _parse_dotenv_line(raw)
        if not parsed:
            continue
        k, v = parsed
        if not override and os.environ.get(k) is not None and str(os.environ.get(k)).strip() != "":
            continue
        os.environ[k] = v
        count += 1
    return count


def _bootstrap_env(extra_env_files: Optional[Iterable[Path]] = None) -> None:
    """
    Populate os.environ from common local .env files if keys are missing.

    Priority:
    1) Existing process env (never overwritten unless override=True in _load_env_file)
    2) Explicit extra env files passed by CLI (first wins among missing keys)
    3) Repo defaults: core/.env then ./.env
    """
    # Optional: python-dotenv if installed (keeps behavior consistent with the rest of the repo)
    try:
        from dotenv import load_dotenv  # type: ignore

        for p in (REPO_ROOT / "core" / ".env", REPO_ROOT / ".env"):
            if p.exists():
                # do not override already-exported vars in the shell
                load_dotenv(dotenv_path=p, override=False)
    except Exception:
        pass

    if extra_env_files:
        for p in extra_env_files:
            _load_env_file(p, override=False)

    # Fallback/manual parse (works even without python-dotenv)
    for p in (REPO_ROOT / "core" / ".env", REPO_ROOT / ".env"):
        _load_env_file(p, override=False)


def _load_sources() -> Dict[str, Any]:
    if not SOURCES_YAML.exists():
        raise FileNotFoundError(f"Missing sources file: {SOURCES_YAML}")
    with SOURCES_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("dataset_sources.yaml must be a YAML mapping at top-level.")
    return data


def _get_roboflow_api_key() -> str:
    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ROBOFLOW_API_KEY is not set.\n"
            "Fix options:\n"
            "  - Export it in PowerShell: $env:ROBOFLOW_API_KEY=\"YOUR_KEY\"\n"
            "  - Or put it in core/.env as: ROBOFLOW_API_KEY=...\n"
            "    (this script auto-loads core/.env and ./.env if present)\n"
        )
    return key


def _find_entry(entries: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for e in entries:
        if str(e.get("name", "")).strip() == name:
            return e
    return None


def list_entries() -> None:
    data = _load_sources()
    entries = data.get("roboflow", [])
    if not isinstance(entries, list):
        raise ValueError("roboflow must be a list in dataset_sources.yaml")
    if not entries:
        print("No roboflow entries found in tools/datasets/dataset_sources.yaml")
        return
    print("Roboflow sources:")
    for e in entries:
        print(
            f"- {e.get('name')}  (workspace={e.get('workspace')}, project={e.get('project')}, "
            f"version={e.get('version')}, format={e.get('format', 'yolov8')})"
        )


def download_one(name: str, *, clean: bool = False, overwrite: bool = True) -> Path:
    data = _load_sources()
    entries = data.get("roboflow", [])
    if not isinstance(entries, list):
        raise ValueError("roboflow must be a list in dataset_sources.yaml")

    entry = _find_entry(entries, name)
    if entry is None:
        raise KeyError(f"Unknown dataset name: {name}. Run with --list to see available names.")

    api_key = _get_roboflow_api_key()
    workspace = str(entry["workspace"])
    project = str(entry["project"])
    version = int(entry["version"])
    fmt = str(entry.get("format", "yolov8"))

    out_dir = RAW_DIR / name
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)

    # CRITICAL (roboflow-python behavior):
    # Version.download(..., overwrite=False) will SKIP download if `location` already exists.
    # Therefore we must NOT pre-create an empty `out_dir` before calling download().

    try:
        from roboflow import Roboflow  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "roboflow package is not installed (required for download).\n"
            "Install with:\n"
            "  pip install roboflow\n"
            f"Original import error: {e}"
        )

    rf = Roboflow(api_key=api_key)
    ds = rf.workspace(workspace).project(project).version(version).download(
        fmt,
        location=str(out_dir),
        overwrite=bool(overwrite),
    )

    # Roboflow returns a dataset object with `location`
    loc = Path(getattr(ds, "location", str(out_dir))).resolve()
    dataset_root = _guess_yolo_dataset_root(loc if loc.exists() else out_dir)

    # If SDK points somewhere unexpected, still prefer a nested data.yaml under out_dir
    if not _has_roboflow_data_file(dataset_root):
        dataset_root = _guess_yolo_dataset_root(out_dir)

    if not _has_roboflow_data_file(dataset_root):
        found = _find_data_yaml_root(out_dir)
        if found is None and loc.exists() and loc != out_dir:
            found = _find_data_yaml_root(loc)
        if found is not None:
            dataset_root = found

    if not _has_roboflow_data_file(dataset_root):
        raise RuntimeError(
            "Download verification failed: missing data.yaml/data.yml after download.\n"
            f"- requested_dir: {out_dir}\n"
            f"- sdk_location:  {loc}\n"
            f"- guessed_root:  {dataset_root}\n"
            f"{_debug_list_dir(out_dir)}\n"
            f"{_debug_list_dir(loc) if loc != out_dir else ''}\n"
            "Tip: re-run with the same command; if this persists, the export may be blocked/quota'd, "
            "or the dataset layout isn't YOLO (try changing format in dataset_sources.yaml)."
        )

    stats = _verify_yolo_export(dataset_root)
    print(f"✅ Downloaded {name}")
    print(f"   - requested_dir: {out_dir}")
    print(f"   - sdk_location:  {loc}")
    print(f"   - dataset_root:  {dataset_root}")
    print(f"   - verify: train_images={stats['train_images']}, train_labels={stats['train_labels']}, "
          f"valid_images={stats['valid_images']}, val_images={stats['val_images']}")
    return dataset_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Roboflow datasets into datasets/raw/")
    parser.add_argument("--list", action="store_true", help="List configured Roboflow datasets")
    parser.add_argument("--name", type=str, default=None, help="Download a single dataset by name")
    parser.add_argument("--all", action="store_true", help="Download all configured datasets")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete datasets/raw/<name>/ before downloading (recommended if a previous attempt left an empty/partial folder).",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Pass overwrite=False to Roboflow (NOT recommended). If the target folder exists, Roboflow may skip downloading entirely.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=None,
        help="Optional extra .env file path(s) to load before reading ROBOFLOW_API_KEY. Can be passed multiple times.",
    )
    args = parser.parse_args()

    extra = [Path(p).expanduser().resolve() for p in (args.env_file or [])]
    _bootstrap_env(extra_env_files=extra)

    if args.list:
        list_entries()
        return

    if args.all and args.name:
        raise SystemExit("Choose either --all or --name (not both).")

    if not args.all and not args.name:
        raise SystemExit("Nothing to do. Use --list, --name <dataset>, or --all.")

    if args.name:
        download_one(args.name, clean=bool(args.clean), overwrite=not bool(args.no_overwrite))
        return

    data = _load_sources()
    entries = data.get("roboflow", [])
    if not isinstance(entries, list):
        raise ValueError("roboflow must be a list in dataset_sources.yaml")
    for e in entries:
        n = str(e.get("name", "")).strip()
        if not n:
            continue
        download_one(n, clean=bool(args.clean), overwrite=not bool(args.no_overwrite))


if __name__ == "__main__":
    main()

