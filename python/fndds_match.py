"""
Match food items to FNDDS foods: hybrid retrieval over a local FNDDS copy
(BM25 + FAISS) and/or the USDA FoodData Central search API.

Input
  <dataset>/food_items.csv   one row per food variable; `search_terms` is a
                             ';'-separated list, each term is matched separately
  local FNDDS (--source local|both)
                             FoodData Central "Survey (FNDDS)" CSV download
                             (food.csv, survey_fndds_food.csv, wweia_food_category.csv),
                             folder set by `fndds_dir` in config/paths.yml
  USDA API (--source api|both)
                             FDC search endpoint restricted to Survey (FNDDS);
                             API key from the FDC_API_KEY environment variable.
                             Responses are cached in cache/usda_api_search/.

Method (per search term)
  recall      local: 1. BM25 over FNDDS descriptions (lexical)
                     2. sentence embedding + FAISS inner product (skip with --no-dense)
              api:   3. USDA FDC search ranking
              -> each source gives its top `--k-retrieve`; fused by reciprocal rank fusion (RRF)
  filter      drop candidates containing an `exclude` word
  rerank      optional cross-encoder score on (search term, description)  [--rerank]
  order       candidates whose description contains the head word (last word
              of the search term) first, then by rerank score (or RRF score)

Offline index: local FNDDS embeddings are cached in cache/ keyed by the FNDDS
content and model, so a new FNDDS release rebuilds the index automatically.

Output (in <dataset>/fndds_match/)
  candidates.csv   top `--top-k` candidates per (var, search_term), with the
                   rank of each candidate in every source (bm25/dense/api)
  matches.csv      the chosen FNDDS food per (var, search_term), with review flags.
                   `manual_fdc_id` and `review_note` are for hand corrections and
                   are kept when the script is re-run; they are the feedback
                   labels for training / evaluating a reranker later.

Usage
  python3 python/fndds_match.py [--dataset datasets/perls9]
         [--source local|api|both] [--no-dense]
         [--model sentence-transformers/all-MiniLM-L6-v2]
         [--rerank [--rerank-model cross-encoder/ms-marco-MiniLM-L-6-v2]]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
KEEP_COLS = ["manual_fdc_id", "review_note"]          # hand-edited columns in matches.csv
SOURCES = ["bm25", "dense", "api"]

STOPWORDS = {"and", "or", "with", "without", "in", "of", "to", "a", "the", "ns", "nfs", "as", "from", "made"}


# ---------------------------------------------------------------------------
# config / io
# ---------------------------------------------------------------------------
def resolve(p: str) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_config(dataset_dir: str, need_local: bool) -> dict:
    paths = yaml.safe_load((PROJECT_ROOT / "config" / "paths.yml").read_text())
    ds = yaml.safe_load((resolve(dataset_dir) / "dataset.yml").read_text())
    if need_local and "fndds_dir" not in paths:
        sys.exit("set `fndds_dir` in config/paths.yml to the FNDDS CSV download folder (or use --source api)")
    return {
        "fndds_dir": resolve(paths["fndds_dir"]) if "fndds_dir" in paths else None,
        "food_items": resolve(ds["food_items"]),
        "out_dir": resolve(ds.get("fndds_match_dir", f"{dataset_dir}/fndds_match")),
    }


def load_fndds(fndds_dir: Path) -> pd.DataFrame:
    """FNDDS foods: fdc_id, food_code, description, wweia_category"""
    def find(name):
        hits = list(fndds_dir.rglob(name))
        if not hits:
            sys.exit(f"{name} not found under {fndds_dir}")
        return hits[0]

    food = pd.read_csv(find("food.csv"), dtype=str)
    food = food[food["data_type"] == "survey_fndds_food"][["fdc_id", "description"]]
    survey = pd.read_csv(find("survey_fndds_food.csv"), dtype=str)
    wweia_col = next((c for c in survey.columns if c.startswith("wweia")), None)
    survey = survey[["fdc_id", "food_code"] + ([wweia_col] if wweia_col else [])]
    out = food.merge(survey, on="fdc_id", how="left")

    cat_files = list(fndds_dir.rglob("wweia_food_category.csv"))
    if wweia_col and cat_files:
        cats = pd.read_csv(cat_files[0], dtype=str)
        cats.columns = ["wweia_code", "wweia_category"] + list(cats.columns[2:])
        out = out.merge(cats[["wweia_code", "wweia_category"]], left_on=wweia_col, right_on="wweia_code", how="left")
    if "wweia_category" not in out:
        out["wweia_category"] = ""
    out = out[["fdc_id", "food_code", "description", "wweia_category"]].fillna("")
    return out.drop_duplicates("fdc_id").reset_index(drop=True)


def load_queries(food_items: Path) -> pd.DataFrame:
    """one row per (var, search_term)"""
    fi = pd.read_csv(food_items, dtype=str, keep_default_na=False)
    rows = []
    for _, r in fi.iterrows():
        for term in [t.strip() for t in r["search_terms"].split(";") if t.strip()]:
            rows.append({"var": r["var"], "search_term": term, "exclude": r["exclude"],
                         "form_label": r["form_label"], "portion": r["portion"]})
    if not rows:
        sys.exit("no search terms in food_items.csv")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------
def lemma(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"                       # berries -> berry
    if len(tok) > 3 and tok.endswith("es") and tok[-3] in "sxz":
        return tok[:-2]                             # boxes -> box
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]                             # beans -> bean
    return tok


def tokenize(text: str) -> list:
    toks = re.findall(r"[a-z0-9]+", str(text).lower())
    return [lemma(t) for t in toks if t not in STOPWORDS]


def head_word(term: str):
    toks = tokenize(term)
    return toks[-1] if toks else None


# ---------------------------------------------------------------------------
# retrievers: search(query, k) -> list of food dicts (best first), each with
#             fdc_id, food_code, description, wweia_category, score
# ---------------------------------------------------------------------------
class LocalRetriever:
    """base for retrievers over the local FNDDS table"""

    def __init__(self, fndds: pd.DataFrame):
        self.fndds = fndds

    def _foods(self, idx, scores):
        out = []
        for i, s in zip(idx, scores):
            f = self.fndds.iloc[int(i)]
            out.append({"fdc_id": f["fdc_id"], "food_code": f["food_code"], "description": f["description"],
                        "wweia_category": f["wweia_category"], "score": float(s)})
        return out


class BM25Retriever(LocalRetriever):
    name = "bm25"

    def __init__(self, fndds):
        super().__init__(fndds)
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi([tokenize(d) for d in fndds["description"]])

    def search(self, query: str, k: int):
        scores = self.bm25.get_scores(tokenize(query))
        idx = np.argsort(-scores)[:k]
        idx = idx[scores[idx] > 0]
        return self._foods(idx, scores[idx])


class DenseRetriever(LocalRetriever):
    """sentence embeddings + FAISS inner-product index (cosine on normalized vectors)"""
    name = "dense"

    def __init__(self, fndds, encoder, cache_dir: Path = None, cache_key: str = ""):
        super().__init__(fndds)
        import faiss
        self.encoder = encoder
        docs = fndds["description"].tolist()
        emb, cache = None, None
        if cache_dir is not None:
            h = hashlib.sha1(("\n".join(docs) + cache_key).encode()).hexdigest()[:12]
            cache = cache_dir / f"fndds_emb_{h}.npy"
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

    def search(self, query: str, k: int):
        scores, idx = self.index.search(self._encode([query]), k)
        keep = idx[0] >= 0
        return self._foods(idx[0][keep], scores[0][keep])


class USDAAPIRetriever:
    """USDA FoodData Central search API, restricted to Survey (FNDDS)"""
    name = "api"

    def __init__(self, api_key: str, cache_dir: Path = None, sleep_sec: float = 0.2, retries: int = 5):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.sleep_sec = sleep_sec
        self.retries = retries
        self.failed = []

    def _get(self, query: str, k: int) -> dict:
        params = {"api_key": self.api_key, "query": query, "dataType": "Survey (FNDDS)",
                  "pageSize": k, "pageNumber": 1}
        url = f"{FDC_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.retries - 1:
                    raise
            except urllib.error.URLError:
                if attempt == self.retries - 1:
                    raise
            time.sleep(min(2 ** attempt, 16))

    def search(self, query: str, k: int):
        cache = None
        if self.cache_dir is not None:
            h = hashlib.sha1(f"{query}|{k}".encode()).hexdigest()[:16]
            cache = self.cache_dir / f"{h}.json"
            if cache.exists():
                return json.loads(cache.read_text())
        try:
            time.sleep(self.sleep_sec)
            res = self._get(query, k)
        except Exception as e:                  # failed queries are reported, not cached
            self.failed.append((query, str(e)))
            return []
        foods = []
        for f in res.get("foods", []):
            foods.append({"fdc_id": str(f.get("fdcId", "")), "food_code": str(f.get("foodCode", "") or ""),
                          "description": f.get("description", ""), "wweia_category": f.get("foodCategory", "") or "",
                          "score": float(f.get("score", 0) or 0)})
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(foods))
        return foods


def cross_encoder_scorer(model_name: str):
    """(query, [descriptions]) -> relevance scores"""
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(model_name)
    return lambda query, docs: model.predict([(query, d) for d in docs])


def sentence_transformer_encoder(model_name: str):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(texts, batch_size=256, show_progress_bar=len(texts) > 1000)


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------
def rrf(rank_lists, k_rrf=60):
    """reciprocal rank fusion: {doc: sum 1/(k + rank)}"""
    fused = {}
    for ranks in rank_lists:
        for r, doc in enumerate(ranks, start=1):
            fused[doc] = fused.get(doc, 0.0) + 1.0 / (k_rrf + r)
    return fused


def match(queries: pd.DataFrame, retrievers: list, k_retrieve=50, top_k=5, reranker=None):
    cand_rows = []
    for _, q in queries.iterrows():
        pool, ranks, scores = {}, {}, {}             # fdc_id -> food / {source: rank} / {source: score}
        rank_lists = []
        for ret in retrievers:
            hits = ret.search(q["search_term"], k_retrieve)
            rank_lists.append([h["fdc_id"] for h in hits])
            for r, h in enumerate(hits, 1):
                pool.setdefault(h["fdc_id"], h)
                if not pool[h["fdc_id"]]["food_code"] and h["food_code"]:
                    pool[h["fdc_id"]] = h            # keep the record with the most information
                ranks.setdefault(h["fdc_id"], {})[ret.name] = r
                scores.setdefault(h["fdc_id"], {})[ret.name] = h["score"]
        fused = rrf(rank_lists)

        excl = [w.strip().lower() for w in q["exclude"].split(";") if w.strip()]
        kept = [d for d in fused if not any(w in pool[d]["description"].lower() for w in excl)]
        rr = {}
        if reranker is not None and kept:
            rr = dict(zip(kept, map(float, reranker(q["search_term"], [pool[d]["description"] for d in kept]))))
        head = head_word(q["search_term"])
        cands = [(d, head is not None and head in set(tokenize(pool[d]["description"]))) for d in kept]
        cands.sort(key=lambda c: (not c[1], -(rr.get(c[0], fused[c[0]]))))

        for rank, (d, head_ok) in enumerate(cands[:top_k], 1):
            f = pool[d]
            row = {"var": q["var"], "search_term": q["search_term"], "rank": rank,
                   "fdc_id": f["fdc_id"], "food_code": f["food_code"], "description": f["description"],
                   "wweia_category": f["wweia_category"],
                   "rrf_score": round(fused[d], 5), "rerank_score": round(rr[d], 4) if d in rr else None,
                   "head_ok": head_ok}
            for s in SOURCES:
                row[f"{s}_rank"] = ranks[d].get(s)
                row[f"{s}_score"] = round(scores[d][s], 3) if s in scores[d] else None
            cand_rows.append(row)
    cols = ["var", "search_term", "rank", "fdc_id", "food_code", "description", "wweia_category",
            "rrf_score", "rerank_score", "head_ok"] + [f"{s}_{x}" for s in SOURCES for x in ("rank", "score")]
    cand = pd.DataFrame(cand_rows, columns=cols)
    for s in SOURCES:
        cand[f"{s}_rank"] = cand[f"{s}_rank"].astype("Int64")
    return cand


def best_matches(queries: pd.DataFrame, cand: pd.DataFrame, sources: list) -> pd.DataFrame:
    top = cand[cand["rank"] == 1].set_index(["var", "search_term"])
    n = cand.groupby(["var", "search_term"]).size()
    out = []
    for _, q in queries.iterrows():
        key = (q["var"], q["search_term"])
        row = {"var": q["var"], "search_term": q["search_term"],
               "form_label": q["form_label"], "portion": q["portion"]}
        if key in top.index:
            t = top.loc[key]
            found = [s for s in sources if not pd.isna(t[f"{s}_rank"])]
            reasons = []
            if not t["head_ok"]:
                reasons.append("head word not in description")
            if len(sources) > 1 and len(found) < len(sources):
                reasons.append("not found by: " + ", ".join(s for s in sources if s not in found))
            if len(found) > 1 and max(t[f"{s}_rank"] for s in found) > 10:
                reasons.append("sources disagree")
            row.update({k: t[k] for k in ["fdc_id", "food_code", "description", "wweia_category",
                                          "rrf_score", "rerank_score", "head_ok"]})
            row.update({f"{s}_rank": t[f"{s}_rank"] for s in SOURCES})
            row["n_candidates"] = int(n.get(key, 0))
            row["needs_review"] = bool(reasons)
            row["review_reason"] = "; ".join(reasons)
        else:
            row.update({"n_candidates": 0, "needs_review": True, "review_reason": "no candidates"})
        out.append(row)
    return pd.DataFrame(out)


def keep_manual_columns(matches: pd.DataFrame, path: Path) -> pd.DataFrame:
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        cols = [c for c in KEEP_COLS if c in old]
        if cols:
            matches = matches.merge(old[["var", "search_term"] + cols], on=["var", "search_term"], how="left")
    for c in KEEP_COLS:
        if c not in matches:
            matches[c] = ""
    matches[KEEP_COLS] = matches[KEEP_COLS].fillna("")
    return matches


def main(argv=None, encoder=None, reranker=None, api_retriever=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--source", choices=["local", "api", "both"], default="local",
                    help="local FNDDS copy, USDA search API, or both (fused)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers model name or local path")
    ap.add_argument("--no-dense", action="store_true", help="local: BM25 only (no embeddings / FAISS)")
    ap.add_argument("--k-retrieve", type=int, default=50, help="candidates taken from each source")
    ap.add_argument("--top-k", type=int, default=5, help="candidates written per search term")
    ap.add_argument("--rerank", action="store_true", help="rerank recalled candidates with a cross-encoder")
    ap.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    args = ap.parse_args(argv)

    use_local = args.source in ("local", "both")
    use_api = args.source in ("api", "both")
    cfg = load_config(args.dataset, need_local=use_local)
    queries = load_queries(cfg["food_items"])

    retrievers, version = [], []
    if use_local:
        fndds = load_fndds(cfg["fndds_dir"])
        version.append(cfg["fndds_dir"].name)
        print(f"local FNDDS: {len(fndds)} foods ({cfg['fndds_dir'].name})")
        retrievers.append(BM25Retriever(fndds))
        if not args.no_dense:
            enc = encoder or sentence_transformer_encoder(args.model)
            retrievers.append(DenseRetriever(fndds, enc, cache_dir=PROJECT_ROOT / "cache", cache_key=args.model))
    if use_api:
        if api_retriever is None:
            key = os.environ.get("FDC_API_KEY", "")
            if not key:
                sys.exit("set the FDC_API_KEY environment variable to use --source api/both")
            api_retriever = USDAAPIRetriever(key, cache_dir=PROJECT_ROOT / "cache" / "usda_api_search")
        api_retriever.failed = []
        version.append("USDA API " + time.strftime("%Y-%m-%d"))
        retrievers.append(api_retriever)
    print(f"{len(queries)} search terms; sources: {', '.join(r.name for r in retrievers)}")

    if args.rerank and reranker is None:
        reranker = cross_encoder_scorer(args.rerank_model)
    cand = match(queries, retrievers, args.k_retrieve, args.top_k, reranker=reranker if args.rerank else None)
    matches = best_matches(queries, cand, sources=[r.name for r in retrievers])

    out = cfg["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    matches = keep_manual_columns(matches, out / "matches.csv")
    matches.insert(len(matches.columns) - len(KEEP_COLS), "fndds_version", " + ".join(version))
    cand.to_csv(out / "candidates.csv", index=False)
    matches.to_csv(out / "matches.csv", index=False)
    print(f"wrote {out.relative_to(PROJECT_ROOT)}/candidates.csv, matches.csv: "
          f"{len(matches)} search terms, {int(matches['needs_review'].sum())} flagged for review")
    if use_api and api_retriever.failed:
        print(f"WARNING: {len(api_retriever.failed)} API queries failed (not cached, retried next run): "
              + "; ".join(q for q, _ in api_retriever.failed[:10]))
    return cand, matches


if __name__ == "__main__":
    main()
