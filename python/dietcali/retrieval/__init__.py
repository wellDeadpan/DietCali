"""Recall sources.

Every retriever has a `name` (used in output columns and the run manifest),
a `version` string, and `search(query, k)` returning a list of Hit dicts,
best first:
    {"fdc_id", "food_code", "description", "wweia_category", "score"}
"""
from .base import Hit, LocalRetriever
from .bm25 import BM25Retriever
from .dense import DenseRetriever, sentence_transformer_encoder
from .usda_api import USDAAPIRetriever

__all__ = ["Hit", "LocalRetriever", "BM25Retriever", "DenseRetriever",
           "sentence_transformer_encoder", "USDAAPIRetriever"]
