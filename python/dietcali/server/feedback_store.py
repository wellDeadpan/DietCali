"""Append-only JSONL store for feedback events (all datasets)."""
from pathlib import Path

from ..core.feedback import FeedbackEvent


class FeedbackStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> list:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [FeedbackEvent.from_json(line) for line in f if line.strip()]

    def append(self, events: list) -> int:
        """append events whose event_id is not stored yet; returns the number written"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        seen = {e.event_id for e in self.read()}
        new = [e for e in events if e.event_id not in seen]
        with open(self.path, "a", encoding="utf-8") as f:
            for e in new:
                f.write(e.to_json() + "\n")
        return len(new)
