from pathlib import Path

import yaml

from ..paths import PROJECT_ROOT, resolve


def load_server_config(path: Path = None, root: Path = PROJECT_ROOT) -> dict:
    """config/server.yml with the server data layout resolved"""
    path = Path(path) if path else root / "config" / "server.yml"
    cfg = yaml.safe_load(path.read_text()) or {}
    server_dir = resolve(cfg.get("server_dir", "server"), root)
    cfg["dirs"] = {
        "root": server_dir,
        "fndds": server_dir / "reference" / "fndds",
        "indexes": server_dir / "indexes",
        "models": server_dir / "models",
        "feedback": server_dir / "feedback",
        "runs": server_dir / "runs",
        "cache": server_dir / "cache",
    }
    return cfg
