"""
Client: send the reviewer's decisions in <dataset>/fndds_match/matches.csv
to the MatchService as feedback events.

Review columns in matches.csv
  review_status   accept   the match (rank 1) is right
                  correct  the right food is manual_fdc_id (any FNDDS fdc_id)
                  none     no FNDDS food fits
  manual_fdc_id   for `correct`
  review_note     free text

Sending twice is safe: identical decisions are stored once.

Usage
  python python/record_feedback.py --reviewer <name> [--dataset datasets/perls9]
"""
import argparse
import sys

import pandas as pd

from dietcali.client import events_from_review, load_dataset, load_queries, load_results
from dietcali.server import MatchService


def main(argv=None, service=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--reviewer", required=True, help="who reviewed (stored with each event)")
    args = ap.parse_args(argv)

    ds = load_dataset(args.dataset)
    sheet_path = ds["results_dir"] / "matches.csv"
    if not sheet_path.exists():
        sys.exit(f"{sheet_path} not found; run python/fndds_match.py first")
    sheet = pd.read_csv(sheet_path, dtype=str, keep_default_na=False)
    q = load_queries(ds["food_items"])
    excludes = dict(zip(zip(q["var"], q["search_term"]), q["exclude"]))
    svc = service or MatchService()

    events, problems = [], []
    for run_id, part in sheet.groupby("run_id"):          # candidates shown in the run each row came from
        run = load_results(ds["results_dir"], run_id)
        ev, pr = events_from_review(part, run["candidates"], ds["name"], args.reviewer,
                                    lookup_foods=svc.lookup_foods, excludes=excludes)
        events += ev
        problems += pr
    n = svc.record_feedback(events)
    reviewed = int((sheet["review_status"].str.strip() != "").sum())
    print(f"{reviewed} reviewed rows -> {len(events)} events, {n} new")
    for p in problems:
        print("  !", p)
    return events, problems


if __name__ == "__main__":
    main()
