"""Evaluation of matching results against the gold set built from feedback."""
from .gold import gold_set
from .metrics import evaluate

__all__ = ["gold_set", "evaluate"]
