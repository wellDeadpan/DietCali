"""Project paths and dataset configuration."""
from pathlib import Path

import yaml


def find_project_root(start: Path = None) -> Path:
    start = Path(start or Path.cwd()).resolve()
    for p in [start, *start.parents]:
        if (p / ".here").exists():
            return p
    raise FileNotFoundError("project root (folder with .here) not found")


PROJECT_ROOT = find_project_root(Path(__file__).parent)


def resolve(p, root: Path = PROJECT_ROOT) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else root / p


def load_paths(root: Path = PROJECT_ROOT) -> dict:
    """config/paths.yml (machine-specific locations)"""
    return yaml.safe_load((root / "config" / "paths.yml").read_text()) or {}


def load_dataset(dataset_dir: str, root: Path = PROJECT_ROOT) -> dict:
    """<dataset>/dataset.yml with the paths this package uses, resolved.

    fndds_match_dir  run outputs (default <dataset>/fndds_match)
    feedback_log     feedback events (default <dataset>/feedback/events.jsonl)
    """
    ds_dir = resolve(dataset_dir, root)
    ds = yaml.safe_load((ds_dir / "dataset.yml").read_text()) or {}
    paths = load_paths(root)
    return {
        "name": ds_dir.name,
        "dir": ds_dir,
        "food_items": resolve(ds["food_items"], root),
        "match_dir": resolve(ds.get("fndds_match_dir", ds_dir / "fndds_match"), root),
        "feedback_log": resolve(ds.get("feedback_log", ds_dir / "feedback" / "events.jsonl"), root),
        "fndds_dir": resolve(paths["fndds_dir"], root) if paths.get("fndds_dir") else None,
    }
