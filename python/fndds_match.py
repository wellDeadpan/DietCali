"""
Match food items to FNDDS foods with local hybrid retrieval (BM25 + FAISS).

Input
  <dataset>/food_items.csv   one row per food variable; `search_terms` is a
                             ';'-separated list, each term is matched separately
  FNDDS CSV download         FoodData Central "Survey (FNDDS)" CSV
                             (food.csv, survey_fndds_food.csv, wweia_food_category.csv)
                             folder set by `fndds_dir` in config/paths.yml

Method (per search term)
  recall      1. BM25 over FNDDS descriptions (lexical)       -> top `--k-retrieve`
              2. sentence embedding + FAISS inner product      -> top `--k-retrieve`
              3. reciprocal rank fusion (RRF) of the two lists
  filter      4. drop candidates containing an `exclude` word
  rerank      5. optional cross-encoder score on (search term, description)  [--rerank]
  order       6. candidates whose description contains the head word (last word
                 of the search term) first, then by rerank score (or RRF score)

Offline index: FNDDS embeddings are cached in cache/ keyed by the FNDDS
content and model, so a new FNDDS release rebuilds the index automatically.

Output (in <dataset>/fndds_match/)
  candidates.csv   top `--top-k` candidates per (var, search_term)
  matches.csv      the chosen FNDDS food per (var, search_term), with review flags.
                   `manual_fdc_id` and `review_note` are for hand corrections and
                   are kept when the script is re-run; they are the feedback
                   labels for training / evaluating a reranker later.

Usage
  python3 python/fndds_match.py [--dataset datasets/perls9] [--no-dense]
         [--model sentence-transformers/all-MiniLM-L6-v2]
         [--rerank [--rerank-model cross-encoder/ms-marco-MiniLM-L-6-v2]]
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
KEEP_COLS = ["manual_fdc_id", "review_note"]          # hand-edited columns in matches.csv

STOPWORDS = {"and", "or", "with", "without", "in", "of", "to", "a", "the", "ns", "nfs", "as", "from", "made"}


# ---------------------------------------------------------------------------
# config / io
# ---------------------------------------------------------------------------
def resolve(p: str) -> Path:
    p = Path(p).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def load_config(dataset_dir: str) -> dict:
    paths = yaml.safe_load((PROJECT_ROOT / "config" / "paths.yml").read_text())
    ds = yaml.safe_load((resolve(dataset_dir) / "dataset.yml").read_text())
    if "fndds_dir" not in paths:
        sys.exit("set `fndds_dir` in config/paths.yml to the FNDDS CSV download folder")
    return {
        "fndds_dir": resolve(paths["fndds_dir"]),
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
# retrievers
# ---------------------------------------------------------------------------
class BM25Retriever:
    def __init__(self, docs):
        from rank_bm25 import BM25Okapi
        self.bm25 = BM25Okapi([tokenize(d) for d in docs])

    def search(self, query: str, k: int):
        scores = self.bm25.get_scores(tokenize(query))
        idx = np.argsort(-scores)[:k]
        idx = idx[scores[idx] > 0]
        return idx, scores[idx]


class DenseRetriever:
    """sentence embeddings + FAISS inner-product index (cosine on normalized vectors)"""

    def __init__(self, docs, encoder, cache_dir: Path = None, cache_key: str = ""):
        import faiss
        self.encoder = encoder
        emb = None
        cache = None
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
        return idx[0][keep], scores[0][keep]


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


def match(queries: pd.DataFrame, fndds: pd.DataFrame, bm25, dense, k_retrieve=50, top_k=5, reranker=None):
    desc_tokens = [set(tokenize(d)) for d in fndds["description"]]
    desc_lower = fndds["description"].str.lower().tolist()
    cand_rows = []
    for _, q in queries.iterrows():
        b_idx, b_sc = bm25.search(q["search_term"], k_retrieve)
        d_idx, d_sc = dense.search(q["search_term"], k_retrieve) if dense else (np.array([], int), np.array([]))
        b_rank = {int(i): r for r, i in enumerate(b_idx, 1)}
        d_rank = {int(i): r for r, i in enumerate(d_idx, 1)}
        b_score = dict(zip(map(int, b_idx), b_sc))
        d_score = dict(zip(map(int, d_idx), d_sc))
        fused = rrf([list(map(int, b_idx)), list(map(int, d_idx))])

        excl = [w.strip().lower() for w in q["exclude"].split(";") if w.strip()]
        head = head_word(q["search_term"])
        kept = [i for i in fused if not any(w in desc_lower[i] for w in excl)]
        rr = {}
        if reranker is not None and kept:
            rr = dict(zip(kept, map(float, reranker(q["search_term"], [fndds.at[i, "description"] for i in kept]))))
        cands = [(i, fused[i], head is not None and head in desc_tokens[i]) for i in kept]
        cands.sort(key=lambda c: (not c[2], -(rr.get(c[0], c[1]))))

        for rank, (i, score, head_ok) in enumerate(cands[:top_k], 1):
            f = fndds.iloc[i]
            cand_rows.append({
                "var": q["var"], "search_term": q["search_term"], "rank": rank,
                "fdc_id": f["fdc_id"], "food_code": f["food_code"], "description": f["description"],
                "wweia_category": f["wweia_category"],
                "rrf_score": round(score, 5), "rerank_score": round(rr[i], 4) if i in rr else None,
                "head_ok": head_ok,
                "bm25_rank": b_rank.get(i), "bm25_score": round(float(b_score[i]), 3) if i in b_score else None,
                "dense_rank": d_rank.get(i), "dense_score": round(float(d_score[i]), 3) if i in d_score else None,
            })
    cand = pd.DataFrame(cand_rows)
    for c in ("bm25_rank", "dense_rank"):
        cand[c] = cand[c].astype("Int64")
    return cand


def best_matches(queries: pd.DataFrame, cand: pd.DataFrame, use_dense: bool) -> pd.DataFrame:
    top = cand[cand["rank"] == 1].set_index(["var", "search_term"])
    n = cand.groupby(["var", "search_term"]).size()
    out = []
    for _, q in queries.iterrows():
        key = (q["var"], q["search_term"])
        row = {"var": q["var"], "search_term": q["search_term"],
               "form_label": q["form_label"], "portion": q["portion"]}
        if key in top.index:
            t = top.loc[key]
            reasons = []
            if not t["head_ok"]:
                reasons.append("head word not in description")
            if use_dense and (pd.isna(t["bm25_rank"]) or pd.isna(t["dense_rank"])):
                reasons.append("found by one retriever only")
            if use_dense and not pd.isna(t["bm25_rank"]) and not pd.isna(t["dense_rank"]) \
                    and max(t["bm25_rank"], t["dense_rank"]) > 10:
                reasons.append("retrievers disagree")
            row.update({k: t[k] for k in ["fdc_id", "food_code", "description", "wweia_category",
                                          "rrf_score", "rerank_score", "head_ok", "bm25_rank", "dense_rank"]})
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


def main(argv=None, encoder=None, reranker=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers model name or local path")
    ap.add_argument("--no-dense", action="store_true", help="BM25 only (no embeddings / FAISS)")
    ap.add_argument("--k-retrieve", type=int, default=50, help="candidates taken from each retriever")
    ap.add_argument("--top-k", type=int, default=5, help="candidates written per search term")
    ap.add_argument("--rerank", action="store_true", help="rerank recalled candidates with a cross-encoder")
    ap.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    args = ap.parse_args(argv)

    cfg = load_config(args.dataset)
    queries = load_queries(cfg["food_items"])
    fndds = load_fndds(cfg["fndds_dir"])
    fndds_version = cfg["fndds_dir"].name
    print(f"{len(queries)} search terms, {len(fndds)} FNDDS foods ({fndds_version})")

    bm25 = BM25Retriever(fndds["description"].tolist())
    dense = None
    if not args.no_dense:
        enc = encoder or sentence_transformer_encoder(args.model)
        dense = DenseRetriever(fndds["description"].tolist(), enc,
                               cache_dir=PROJECT_ROOT / "cache", cache_key=args.model)

    if args.rerank and reranker is None:
        reranker = cross_encoder_scorer(args.rerank_model)
    cand = match(queries, fndds, bm25, dense, args.k_retrieve, args.top_k,
                 reranker=reranker if args.rerank else None)
    matches = best_matches(queries, cand, use_dense=dense is not None)

    out = cfg["out_dir"]
    out.mkdir(parents=True, exist_ok=True)
    matches = keep_manual_columns(matches, out / "matches.csv")
    matches.insert(len(matches.columns) - len(KEEP_COLS), "fndds_version", fndds_version)
    cand.to_csv(out / "candidates.csv", index=False)
    matches.to_csv(out / "matches.csv", index=False)
    print(f"wrote {out.relative_to(PROJECT_ROOT)}/candidates.csv, matches.csv: "
          f"{len(matches)} search terms, {int(matches['needs_review'].sum())} flagged for review")
    return cand, matches


if __name__ == "__main__":
    main()
