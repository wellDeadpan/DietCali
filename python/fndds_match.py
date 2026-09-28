"""
Match food items to FNDDS foods (one match per search term) and write a run.

Recall from a local FNDDS copy (BM25 + FAISS) and/or the USDA search API,
fused with RRF; exclude-word filter; head-word rule; optional cross-encoder.
See python/dietcali/pipeline.py for the method and output layout.

Usage
  python3 python/fndds_match.py [--dataset datasets/perls9]
         [--source local|api|both] [--no-dense]
         [--model sentence-transformers/all-MiniLM-L6-v2]
         [--rerank [--rerank-model cross-encoder/ms-marco-MiniLM-L-6-v2]]

Then review <dataset>/fndds_match/matches.csv (review_status / manual_fdc_id /
review_note), record it with python/record_feedback.py and score runs with
python/evaluate.py.
"""
import argparse
import os
import sys

import pandas as pd

from dietcali import config, fndds
from dietcali.pipeline import Matcher, best_matches, new_run_id, write_run
from dietcali.rerank import CrossEncoderReranker
from dietcali.retrieval import BM25Retriever, DenseRetriever, USDAAPIRetriever, sentence_transformer_encoder

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def load_queries(food_items) -> pd.DataFrame:
    """food_items.csv -> one row per (var, search_term)"""
    fi = pd.read_csv(food_items, dtype=str, keep_default_na=False)
    rows = [{"var": r["var"], "search_term": t.strip(), "exclude": r["exclude"],
             "form_label": r["form_label"], "portion": r["portion"]}
            for _, r in fi.iterrows() for t in r["search_terms"].split(";") if t.strip()]
    if not rows:
        sys.exit("no search terms in food_items.csv")
    return pd.DataFrame(rows)


def main(argv=None, encoder=None, reranker=None, api_retriever=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--source", choices=["local", "api", "both"], default="local")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers model name or local path")
    ap.add_argument("--no-dense", action="store_true", help="local: BM25 only (no embeddings / FAISS)")
    ap.add_argument("--k-retrieve", type=int, default=50, help="candidates taken from each source")
    ap.add_argument("--top-k", type=int, default=5, help="candidates kept per search term")
    ap.add_argument("--rerank", action="store_true", help="rerank recalled candidates with a cross-encoder")
    ap.add_argument("--rerank-model", default=DEFAULT_RERANK_MODEL)
    args = ap.parse_args(argv)

    ds = config.load_dataset(args.dataset)
    queries = load_queries(ds["food_items"])
    retrievers, fndds_version = [], ""
    if args.source in ("local", "both"):
        if ds["fndds_dir"] is None:
            sys.exit("set `fndds_dir` in config/paths.yml (python/download_fndds.py --update-config), or use --source api")
        foods = fndds.load_foods(ds["fndds_dir"])
        fndds_version = fndds.version_of(ds["fndds_dir"], foods)
        print(f"local FNDDS: {len(foods)} foods ({fndds_version})")
        retrievers.append(BM25Retriever(foods))
        if not args.no_dense:
            retrievers.append(DenseRetriever(foods, encoder or sentence_transformer_encoder(args.model), args.model,
                                             cache_dir=config.PROJECT_ROOT / "cache"))
    if args.source in ("api", "both"):
        if api_retriever is None:
            key = os.environ.get("FDC_API_KEY", "")
            if not key:
                sys.exit("set the FDC_API_KEY environment variable to use --source api/both")
            api_retriever = USDAAPIRetriever(key, cache_dir=config.PROJECT_ROOT / "cache" / "usda_api_search")
        api_retriever.failed = []
        retrievers.append(api_retriever)
    if args.rerank and reranker is None:
        reranker = CrossEncoderReranker(args.rerank_model)

    matcher = Matcher(retrievers, reranker if args.rerank else None, args.k_retrieve, args.top_k,
                      fndds_version=fndds_version)
    run_id = new_run_id()
    print(f"run {run_id}: {len(queries)} search terms; sources: {', '.join(matcher.sources)}"
          + ("; rerank" if matcher.reranker else ""))
    cand = matcher.match(queries, run_id)
    matches = best_matches(queries, cand, matcher.sources)
    run_dir = write_run(ds["match_dir"], run_id, cand, matches,
                        matcher.manifest(run_id, ds["name"], ds["food_items"]))

    print(f"wrote {run_dir.relative_to(config.PROJECT_ROOT)} and {ds['match_dir'].relative_to(config.PROJECT_ROOT)}/matches.csv: "
          f"{int(matches['needs_review'].sum())} of {len(matches)} flagged for review")
    if api_retriever is not None and api_retriever.failed:
        print(f"WARNING: {len(api_retriever.failed)} API queries failed (not cached, retried next run): "
              + "; ".join(q for q, _ in api_retriever.failed[:10]))
    return run_id, cand, matches


if __name__ == "__main__":
    main()
