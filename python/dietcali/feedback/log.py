from pathlib import Path

from .schema import FeedbackEvent


def read_events(path: Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [FeedbackEvent.from_json(line) for line in f if line.strip()]


def append_events(path: Path, events: list) -> int:
    """append events whose event_id is not in the log yet; returns the number written"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = {e.event_id for e in read_events(path)}
    new = [e for e in events if e.event_id not in seen]
    with open(path, "a", encoding="utf-8") as f:
        for e in new:
            f.write(e.to_json() + "\n")
    return len(new)


def latest_by_query(events: list, label_sources=("expert",)) -> dict:
    """query key -> most recent event (later decisions supersede earlier ones)"""
    out = {}
    for e in sorted(events, key=lambda e: e.timestamp):
        if label_sources and e.label_source not in label_sources:
            continue
        out[e.key] = e
    return out
