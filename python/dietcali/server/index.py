"""Offline index per (FNDDS release, embedding model).

indexes/<release>/<model slug>/
  foods.csv        the food table the embeddings were built from
  embeddings.npy   normalized food-description embeddings
  meta.json        release, release content hash, model, n, dim, built time
"""
import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.retrieval import normalize


def slug(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "__", model_name)


def index_dir(indexes_root: Path, release: str, model_name: str) -> Path:
    return Path(indexes_root) / release / slug(model_name)


def build_index(indexes_root: Path, release: str, release_version: str, foods: pd.DataFrame,
                model_name: str, encoder) -> Path:
    d = index_dir(indexes_root, release, model_name)
    d.mkdir(parents=True, exist_ok=True)
    emb = normalize(encoder(foods["description"].tolist()))
    foods.to_csv(d / "foods.csv", index=False)
    np.save(d / "embeddings.npy", emb)
    (d / "meta.json").write_text(json.dumps({
        "release": release, "release_version": release_version, "model": model_name,
        "n": int(len(foods)), "dim": int(emb.shape[1]), "built": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2))
    return d


def load_index(indexes_root: Path, release: str, model_name: str):
    """-> (foods, embeddings, meta); raises if the index was not built"""
    d = index_dir(indexes_root, release, model_name)
    if not (d / "meta.json").exists():
        raise FileNotFoundError(f"no index for {release} / {model_name}; run python/server_build_index.py")
    foods = pd.read_csv(d / "foods.csv", dtype=str, keep_default_na=False)
    return foods, np.load(d / "embeddings.npy"), json.loads((d / "meta.json").read_text())
