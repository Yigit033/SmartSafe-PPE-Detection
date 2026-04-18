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
  python tools/datasets/download_roboflow.py --all

Notes:
- This script uses the official `roboflow` Python SDK if installed.
  If missing, install it:
    pip install roboflow
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_YAML = REPO_ROOT / "tools" / "datasets" / "dataset_sources.yaml"
RAW_DIR = REPO_ROOT / "datasets" / "raw"


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
            "ROBOFLOW_API_KEY is not set. Set it in your shell before running.\n"
            "PowerShell example:\n"
            '  $env:ROBOFLOW_API_KEY="YOUR_KEY"\n'
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


def download_one(name: str) -> Path:
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
    out_dir.mkdir(parents=True, exist_ok=True)

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
    )

    # Roboflow returns a dataset object with `location`
    loc = Path(getattr(ds, "location", str(out_dir))).resolve()
    print(f"✅ Downloaded {name} to: {loc}")
    return loc


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Roboflow datasets into datasets/raw/")
    parser.add_argument("--list", action="store_true", help="List configured Roboflow datasets")
    parser.add_argument("--name", type=str, default=None, help="Download a single dataset by name")
    parser.add_argument("--all", action="store_true", help="Download all configured datasets")
    args = parser.parse_args()

    if args.list:
        list_entries()
        return

    if args.all and args.name:
        raise SystemExit("Choose either --all or --name (not both).")

    if not args.all and not args.name:
        raise SystemExit("Nothing to do. Use --list, --name <dataset>, or --all.")

    if args.name:
        download_one(args.name)
        return

    data = _load_sources()
    entries = data.get("roboflow", [])
    if not isinstance(entries, list):
        raise ValueError("roboflow must be a list in dataset_sources.yaml")
    for e in entries:
        n = str(e.get("name", "")).strip()
        if not n:
            continue
        download_one(n)


if __name__ == "__main__":
    main()

