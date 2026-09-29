"""Project root and path resolution (shared by all layers)."""
from pathlib import Path


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
