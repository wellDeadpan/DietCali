"""Small JSON registries with an `active` entry (FNDDS releases, models)."""
import json
import time
from pathlib import Path


class Registry:
    """{"active": name, "entries": {name: {...metadata}}}"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"active": None, "entries": {}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))

    @property
    def active(self):
        return self.data["active"]

    @property
    def entries(self) -> dict:
        return self.data["entries"]

    def register(self, name: str, **meta):
        self.entries[name] = {**self.entries.get(name, {}), **meta,
                              "registered": self.entries.get(name, {}).get("registered") or time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.save()

    def activate(self, name: str):
        if name not in self.entries:
            raise KeyError(f"{name} is not registered ({self.path})")
        self.data["active"] = name
        self.entries[name]["activated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.save()


class ModelRegistry:
    """one Registry per model kind (embedding, reranker) in models/registry.json"""
    KINDS = ("embedding", "reranker")

    def __init__(self, path: Path, defaults: dict):
        self.path = Path(path)
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}
        changed = False
        for kind in self.KINDS:
            if kind not in self.data:
                self.data[kind] = {"active": None, "entries": {}}
            if not self.data[kind]["active"] and defaults.get(kind):
                name = defaults[kind]
                self.data[kind]["entries"].setdefault(name, {"source": "default", "registered": time.strftime("%Y-%m-%dT%H:%M:%S")})
                self.data[kind]["active"] = name
                changed = True
        if changed:
            self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))

    def active(self, kind: str) -> str:
        return self.data[kind]["active"]

    def register(self, kind: str, name: str, **meta):
        self.data[kind]["entries"][name] = {**self.data[kind]["entries"].get(name, {}), **meta}
        self.save()

    def activate(self, kind: str, name: str):
        if name not in self.data[kind]["entries"]:
            raise KeyError(f"{kind} model {name} is not registered")
        self.data[kind]["active"] = name
        self.save()
