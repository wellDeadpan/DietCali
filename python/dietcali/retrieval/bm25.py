import numpy as np

from ..text import tokenize
from .base import LocalRetriever


class BM25Retriever(LocalRetriever):
    """lexical recall: BM25 (Okapi) over FNDDS descriptions"""
    name = "bm25"
    version = "bm25okapi"

    def __init__(self, foods):
        super().__init__(foods)
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi([tokenize(d) for d in foods["description"]])

    def search(self, query, k):
        scores = self.bm25.get_scores(tokenize(query))
        idx = np.argsort(-scores)[:k]
        idx = idx[scores[idx] > 0]
        return self._hits(idx, scores[idx])
