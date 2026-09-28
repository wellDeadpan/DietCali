"""Feedback: every human decision about a match is stored as an event.

Events are appended to a JSONL log (one event per line) and never edited;
a later event for the same query supersedes an earlier one. Each event keeps
what the system showed (candidates, run_id, component versions via the run
manifest), so it can be used as training data (positives + shown-but-not-
chosen hard negatives) and as a gold set for evaluation.
"""
from .schema import SCHEMA_VERSION, FeedbackEvent, query_key
from .log import append_events, latest_by_query, read_events
from .from_review import events_from_review

__all__ = ["SCHEMA_VERSION", "FeedbackEvent", "query_key", "append_events", "latest_by_query",
           "read_events", "events_from_review"]
