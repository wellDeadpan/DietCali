"""
Score a matching run against the gold set (expert feedback events).

Metrics (over gold queries that have a correct FNDDS food)
  top1        rank-1 candidate is the gold food
  recall@k    gold food within the first k candidates
  mrr         mean reciprocal rank of the gold food (0 if not shown)
  found_by_*  share of gold foods that each recall source retrieved
A candidate counts as gold if its food_code matches (fdc_id if a code is missing).

Usage
  python3 python/evaluate.py [--dataset datasets/perls9] [--run latest|<run_id>]
         [--label-source expert [user ...]] [--by-group]
Writes <run>/eval.json.
"""
import argparse
import json
import sys

import pandas as pd

from dietcali import config
from dietcali.eval import evaluate, gold_set
from dietcali.feedback import read_events
from dietcali.pipeline import load_run


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--run", default="latest")
    ap.add_argument("--label-source", nargs="+", default=["expert"])
    ap.add_argument("--by-group", action="store_true", help="break down by questionnaire section (food_group)")
    args = ap.parse_args(argv)

    ds = config.load_dataset(args.dataset)
    gold = gold_set(read_events(ds["feedback_log"]), ds["name"], tuple(args.label_source))
    if gold.empty:
        sys.exit(f"no gold labels in {ds['feedback_log']}; review matches.csv and run python/record_feedback.py")
    run = load_run(ds["match_dir"], args.run)

    group = None
    if args.by_group:
        fi = pd.read_csv(ds["food_items"], dtype=str, keep_default_na=False)
        group = fi.set_index("var")["food_group"]
    result = evaluate(run["candidates"], gold, group=group)
    result.update({"run_id": run["run_id"], "manifest": run["manifest"], "label_sources": args.label_source,
                   "n_gold": len(gold)})
    (run["dir"] / "eval.json").write_text(json.dumps(result, indent=2))

    o = result["overall"]
    print(f"run {run['run_id']}  gold: {len(gold)} labels ({result['not_scored_none']} 'none' not scored, "
          f"{result['gold_not_in_run']} not in this run)")
    print("  " + "  ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in o.items()))
    for g, m in (result.get("by_group") or {}).items():
        print(f"  {g:<40} n={m['n']:<4} top1={m.get('top1', 0):.2f}  mrr={m.get('mrr', 0):.2f}")
    return result


if __name__ == "__main__":
    main()
