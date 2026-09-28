import hashlib
from pathlib import Path

import numpy as np

from .base import LocalRetriever


def sentence_transformer_encoder(model_name: str):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(texts, batch_size=256, show_progress_bar=len(texts) > 1000)


class DenseRetriever(LocalRetriever):
    """semantic recall: sentence embeddings + FAISS inner-product index
    (cosine on normalized vectors). Embeddings are cached per food list + model."""
    name = "dense"

    def __init__(self, foods, encoder, model_name: str, cache_dir: Path = None):
        super().__init__(foods)
        import faiss
        self.encoder = encoder
        self.version = model_name
        docs = foods["description"].tolist()
        emb, cache = None, None
        if cache_dir is not None:
            h = hashlib.sha1(("\n".join(docs) + model_name).encode()).hexdigest()[:12]
            cache = Path(cache_dir) / f"fndds_emb_{h}.npy"
            if cache.exists():
                emb = np.load(cache)
        if emb is None:
            emb = self._encode(docs)
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                np.save(cache, emb)
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)

    def _encode(self, texts):
        emb = np.asarray(self.encoder(list(texts)), dtype="float32")
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        return emb / np.clip(norms, 1e-12, None)

    def search(self, query, k):
        scores, idx = self.index.search(self._encode([query]), k)
        keep = idx[0] >= 0
        return self._hits(idx[0][keep], scores[0][keep])
