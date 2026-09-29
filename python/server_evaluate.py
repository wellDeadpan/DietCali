"""
Server job: score matching against the expert feedback (gold set).

  --run RUN_ID                          score a stored run
  --dataset NAME [settings]             re-match that dataset's gold queries with the given
                                        settings and score them, e.g. before activating:
                                          --release 2026-10-31
                                          --model <embedding model>   --reranker <model> --rerank
                                          --sources bm25 dense api

Metrics: top1, recall@k (gold within the first k), mrr, found_by_<source>.
A candidate counts as gold if its food_code matches (fdc_id if a code is missing),
so labels made on an older FNDDS release still apply.
"""
import argparse

from dietcali.server import MatchService


def main(argv=None, service=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run")
    ap.add_argument("--dataset")
    ap.add_argument("--release")
    ap.add_argument("--model", help="embedding model")
    ap.add_argument("--reranker", help="reranker model")
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--sources", nargs="+")
    ap.add_argument("--label-source", nargs="+", default=["expert"])
    args = ap.parse_args(argv)
    if not (args.run or args.dataset):
        ap.error("give --run or --dataset")
    svc = service or MatchService()

    if args.run:
        res = svc.evaluate_run(args.run, args.label_source)
    else:
        res = svc.evaluate_config(args.dataset, args.label_source, release=args.release,
                                  embedding_model=args.model, reranker_model=args.reranker,
                                  rerank=args.rerank or None, sources=args.sources)
    o = res["overall"]
    man = res["manifest"]
    print(f"run {res['run_id']} ({res['dataset']}; FNDDS {man['fndds_version']}; {man['retrievers']}; "
          f"reranker {man['reranker']})")
    print(f"gold: {res['n_gold']} labels ({res['not_scored_none']} 'none' not scored, "
          f"{res['gold_not_in_run']} not in this run)")
    print("  " + "  ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in o.items()))
    return res


if __name__ == "__main__":
    main()
