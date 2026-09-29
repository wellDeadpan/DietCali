"""MatchService: the only thing clients call.

Today it runs in-process; the methods map 1:1 to future HTTP endpoints:
  match(queries, dataset, ...)      POST /match
  lookup_foods(fdc_ids)             GET  /foods
  record_feedback(events)           POST /feedback
  evaluate_run(run_id)              (server-internal)
  evaluate_config(dataset, ...)     (server-internal: score a release / model before activating it)
"""
import json
import os
import time

import pandas as pd

from ..core.eval import evaluate, gold_set
from ..core.feedback import latest_by_query
from ..core.matcher import Matcher
from ..core.rerank import CrossEncoderReranker
from ..core.retrieval import BM25Retriever, DenseRetriever, USDAAPIRetriever
from .config import load_server_config
from .feedback_store import FeedbackStore
from .index import build_index, load_index
from .reference import FNDDSReference
from .registry import ModelRegistry
from .runs import git_commit, load_run, new_run_id, save_run

LOCAL_SOURCES = {"bm25", "dense"}
ALL_SOURCES = LOCAL_SOURCES | {"api"}


def sentence_transformer_encoder(model_name: str):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(list(texts), batch_size=256, show_progress_bar=len(texts) > 1000)


class MatchService:
    def __init__(self, cfg: dict = None, encoder_factory=None, reranker_factory=None, api_retriever=None):
        """factories are injectable for tests: model name -> encoder(texts) / reranker"""
        self.cfg = cfg or load_server_config()
        dirs = self.cfg["dirs"]
        self.reference = FNDDSReference(self.cfg)
        self.models = ModelRegistry(dirs["models"] / "registry.json", self.cfg.get("models", {}))
        self.feedback = FeedbackStore(dirs["feedback"] / "events.jsonl")
        self.encoder_factory = encoder_factory or sentence_transformer_encoder
        self.reranker_factory = reranker_factory or CrossEncoderReranker
        self._api = api_retriever
        self._cache = {}

    # ------------------------------------------------------------------ components
    def _cached(self, key, make):
        if key not in self._cache:
            self._cache[key] = make()
        return self._cache[key]

    def _encoder(self, model):
        return self._cached(("encoder", model), lambda: self.encoder_factory(model))

    def _bm25(self, release):
        return self._cached(("bm25", release), lambda: BM25Retriever(self.reference.foods(release)))

    def _dense(self, release, model):
        def make():
            foods, emb, meta = load_index(self.cfg["dirs"]["indexes"], release, model)
            if meta["release_version"] != self.reference.version(release):
                raise RuntimeError(f"index for {release} / {model} is out of date; run python/server_build_index.py")
            return DenseRetriever(foods, emb, self._encoder(model), model)
        return self._cached(("dense", release, model), make)

    def _reranker(self, model):
        return self._cached(("reranker", model), lambda: self.reranker_factory(model))

    def _api_retriever(self):
        if self._api is None:
            env = self.cfg.get("usda_api", {}).get("api_key_env", "FDC_API_KEY")
            key = os.environ.get(env, "")
            if not key:
                raise RuntimeError(f"set the {env} environment variable to use the api source")
            self._api = USDAAPIRetriever(key, cache_dir=self.cfg["dirs"]["cache"] / "usda_api_search")
        return self._api

    # ------------------------------------------------------------------ matching
    def match(self, queries: pd.DataFrame, dataset: str, sources=None, rerank=None, top_k=None, k_retrieve=None,
              release=None, embedding_model=None, reranker_model=None) -> dict:
        """queries: var, search_term, exclude (+ form_label, portion)
        -> {"run_id", "manifest", "candidates"}; the run is also stored on the server"""
        m = self.cfg.get("matching", {})
        sources = list(sources or m.get("sources", ["bm25", "dense"]))
        bad = set(sources) - ALL_SOURCES
        if bad:
            raise ValueError(f"unknown sources {sorted(bad)}; use {sorted(ALL_SOURCES)}")
        rerank = m.get("rerank", False) if rerank is None else rerank
        release = release or (self.reference.active() if LOCAL_SOURCES & set(sources) else None)
        embedding_model = embedding_model or self.models.active("embedding")
        reranker_model = reranker_model or self.models.active("reranker")

        retrievers = []
        if "bm25" in sources:
            retrievers.append(self._bm25(release))
        if "dense" in sources:
            retrievers.append(self._dense(release, embedding_model))
        if "api" in sources:
            api = self._api_retriever()
            api.failed = []
            retrievers.append(api)
        matcher = Matcher(retrievers, self._reranker(reranker_model) if rerank else None,
                          k_retrieve or m.get("k_retrieve", 50), top_k or m.get("top_k", 5))

        run_id = new_run_id()
        cand = matcher.match(queries, run_id)
        manifest = {
            "run_id": run_id,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "request": {"dataset": dataset, "n_queries": int(len(queries)), "sources": sources, "rerank": bool(rerank)},
            "fndds_version": self.reference.version(release) if release else None,
            **matcher.components(),
            "code_version": git_commit(),
            "warnings": [f"api query failed: {q}" for q, _ in getattr(self._api, "failed", [])] if "api" in sources else [],
        }
        save_run(self.cfg["dirs"]["runs"], manifest, cand)
        return {"run_id": run_id, "manifest": manifest, "candidates": cand}

    def lookup_foods(self, fdc_ids, release=None) -> pd.DataFrame:
        """FNDDS food records for fdc_ids (e.g. a reviewer's manual correction)"""
        foods = self.reference.foods(release)
        return foods[foods["fdc_id"].isin([str(i) for i in fdc_ids])].reset_index(drop=True)

    # ------------------------------------------------------------------ feedback / evaluation
    def record_feedback(self, events: list) -> int:
        return self.feedback.append(events)

    def gold(self, dataset: str, label_sources=("expert",)) -> pd.DataFrame:
        return gold_set(self.feedback.read(), dataset, tuple(label_sources))

    def evaluate_run(self, run_id: str, label_sources=("expert",), group=None) -> dict:
        run = load_run(self.cfg["dirs"]["runs"], run_id)
        dataset = run["manifest"]["request"]["dataset"]
        gold = self.gold(dataset, label_sources)
        result = {"run_id": run_id, "dataset": dataset, "n_gold": len(gold), "label_sources": list(label_sources),
                  "manifest": run["manifest"], **evaluate(run["candidates"], gold, group=group)}
        (run["dir"] / "eval.json").write_text(json.dumps(result, indent=2, default=str))
        return result

    def evaluate_config(self, dataset: str, label_sources=("expert",), group=None, **match_kwargs) -> dict:
        """re-match the gold queries of a dataset with the given settings (e.g. a new
        release or model, not yet active) and score them"""
        events = latest_by_query(self.feedback.read(), tuple(label_sources))
        rows = [{"var": var, "search_term": q, "exclude": e.context.get("exclude", ""),
                 "form_label": e.context.get("form_label", ""), "portion": e.context.get("portion", "")}
                for (ds, var, q), e in events.items() if ds == dataset]
        if not rows:
            raise RuntimeError(f"no {'/'.join(label_sources)} feedback for dataset {dataset}")
        run = self.match(pd.DataFrame(rows), dataset, **match_kwargs)
        return self.evaluate_run(run["run_id"], label_sources, group)

    # ------------------------------------------------------------------ offline jobs
    def build_index(self, release=None, embedding_model=None):
        release = release or self.reference.active()
        model = embedding_model or self.models.active("embedding")
        return build_index(self.cfg["dirs"]["indexes"], release, self.reference.version(release),
                           self.reference.foods(release), model, self._encoder(model))
