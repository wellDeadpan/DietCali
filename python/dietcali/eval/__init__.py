"""Evaluation of a matching run against the gold set built from feedback."""
from .gold import gold_set
from .metrics import evaluate

__all__ = ["gold_set", "evaluate"]
