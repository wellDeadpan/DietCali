import numpy as np

from .base import LocalRetriever


def normalize(emb) -> np.ndarray:
    emb = np.asarray(emb, dtype="float32")
    return emb / np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-12, None)


class DenseRetriever(LocalRetriever):
    """semantic recall: FAISS inner-product index over precomputed, normalized
    food embeddings (built offline by the server); `encoder` embeds queries
    with the same model."""
    name = "dense"

    def __init__(self, foods, embeddings: np.ndarray, encoder, model_name: str):
        super().__init__(foods)
        import faiss
        if len(embeddings) != len(foods):
            raise ValueError("embeddings do not match the food table")
        self.encoder = encoder
        self.version = model_name
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(np.asarray(embeddings, dtype="float32"))

    def search(self, query, k):
        scores, idx = self.index.search(normalize(self.encoder([query])), k)
        keep = idx[0] >= 0
        return self._hits(idx[0][keep], scores[0][keep])
