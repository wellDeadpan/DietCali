"""
Client: match this dataset's food items to FNDDS foods (one match per search term).

Sends the queries from <dataset>/food_items.csv to the MatchService and writes
what comes back to <dataset>/fndds_match/ (review sheet matches.csv, candidates,
manifest, runs/<run_id>/). FNDDS data, indexes and models are the server's
business (server_update_fndds.py, server_build_index.py).

Usage
  python python/fndds_match.py [--dataset datasets/perls9] [--sources bm25 dense api] [--rerank] [--top-k 5]

Then fill in the review columns of matches.csv and run python/record_feedback.py.
"""
import argparse

from dietcali.client import load_dataset, load_queries, write_results
from dietcali.core.matcher import best_matches
from dietcali.paths import PROJECT_ROOT
from dietcali.server import MatchService


def main(argv=None, service=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--sources", nargs="+", help="bm25 dense api (default: server setting)")
    ap.add_argument("--rerank", action="store_true", help="cross-encoder rerank (default: server setting)")
    ap.add_argument("--top-k", type=int)
    args = ap.parse_args(argv)

    ds = load_dataset(args.dataset)
    queries = load_queries(ds["food_items"])
    svc = service or MatchService()
    run = svc.match(queries, ds["name"], sources=args.sources, rerank=args.rerank or None, top_k=args.top_k)
    man = run["manifest"]
    matches = best_matches(queries, run["candidates"], man["request"]["sources"])
    run_dir = write_results(ds["results_dir"], run, matches)

    print(f"run {run['run_id']}: {len(queries)} search terms; FNDDS {man['fndds_version']}; "
          f"sources {man['request']['sources']}" + ("; rerank" if man["reranker"] else ""))
    print(f"wrote {run_dir.relative_to(PROJECT_ROOT)} and {(ds['results_dir'] / 'matches.csv').relative_to(PROJECT_ROOT)}: "
          f"{int(matches['needs_review'].sum())} of {len(matches)} flagged for review")
    for w in man.get("warnings", []):
        print("WARNING:", w)
    return run, matches


if __name__ == "__main__":
    main()
