import hashlib
import json
import time
from dataclasses import asdict, dataclass, field

SCHEMA_VERSION = 1
OUTCOMES = {"accept", "correct", "none"}      # top match right / reviewer picked another food / no FNDDS food fits
LABEL_SOURCES = {"expert", "user"}            # expert review (high trust) vs app user choice (noisy, position-biased)


@dataclass
class FeedbackEvent:
    """One decision about the match for one query.

    query     the text that was matched (search term, or user input in an app)
    context   where the query comes from, e.g. {"dataset", "var", "form_label", "portion"}
    shown     candidates shown, best first: [{"rank", "fdc_id", "food_code", "description"}]
    outcome   accept | correct | none
    selected  the right food {"fdc_id", "food_code", "description"}; None for outcome none.
              food_code is stored because fdc_ids change between FNDDS releases.
    """
    query: str
    context: dict
    outcome: str
    label_source: str
    run_id: str = ""
    shown: list = field(default_factory=list)
    selected: dict = None
    reviewer: str = ""
    note: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    schema_version: int = SCHEMA_VERSION
    event_id: str = ""

    def __post_init__(self):
        if self.outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {sorted(OUTCOMES)}, got {self.outcome!r}")
        if self.label_source not in LABEL_SOURCES:
            raise ValueError(f"label_source must be one of {sorted(LABEL_SOURCES)}, got {self.label_source!r}")
        if self.outcome != "none" and not (self.selected and self.selected.get("fdc_id")):
            raise ValueError(f"outcome {self.outcome!r} needs a selected food")
        if not self.event_id:
            sel = (self.selected or {}).get("fdc_id", "")
            # run_id is not part of the id: a decision carried over to a re-run is the same decision
            raw = "|".join([json.dumps(self.context, sort_keys=True), self.query,
                            self.outcome, sel, self.label_source, self.reviewer, self.note])
            self.event_id = hashlib.sha1(raw.encode()).hexdigest()[:16]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "FeedbackEvent":
        return cls(**json.loads(line))

    @property
    def key(self) -> tuple:
        return query_key(self.context, self.query)


def query_key(context: dict, query: str) -> tuple:
    """identity of a query across runs: dataset + variable + text"""
    return (context.get("dataset", ""), context.get("var", ""), query)
