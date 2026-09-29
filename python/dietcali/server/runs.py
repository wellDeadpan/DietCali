"""Server-side record of every match request: runs/<run_id>/{manifest.json, candidates.csv}."""
import json
import subprocess
import time
from pathlib import Path

import pandas as pd

from ..paths import PROJECT_ROOT


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1000000:06d}"


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "") if out.returncode == 0 else ""
    except Exception:
        return ""


def save_run(runs_root: Path, manifest: dict, cand: pd.DataFrame) -> Path:
    d = Path(runs_root) / manifest["run_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    cand.to_csv(d / "candidates.csv", index=False)
    return d


def load_run(runs_root: Path, run_id: str) -> dict:
    d = Path(runs_root) / run_id
    if not d.exists():
        raise FileNotFoundError(f"run {run_id} not found in {runs_root}")
    return {"run_id": run_id, "dir": d,
            "manifest": json.loads((d / "manifest.json").read_text()),
            "candidates": pd.read_csv(d / "candidates.csv", dtype=str, keep_default_na=False)}


def list_runs(runs_root: Path, dataset: str = None) -> list:
    """run manifests, oldest first (optionally only one dataset)"""
    out = []
    for m in sorted(Path(runs_root).glob("*/manifest.json")):
        man = json.loads(m.read_text())
        if dataset is None or man.get("request", {}).get("dataset") == dataset:
            out.append(man)
    return out
