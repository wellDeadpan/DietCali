"""Candidate filtering and ordering after recall.

rules          exclude-word filter, head-word check (deterministic)
cross_encoder  optional learned reranker: score(query, [descriptions]) -> scores
A reranker is any object with `name`, `version` and `score(query, docs)`.
"""
from .cross_encoder import CrossEncoderReranker
from .rules import excluded, head_ok, parse_exclude

__all__ = ["CrossEncoderReranker", "excluded", "head_ok", "parse_exclude"]
