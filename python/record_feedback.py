"""
Record the reviewer's decisions in <dataset>/fndds_match/matches.csv as
feedback events (appended to <dataset>/feedback/events.jsonl).

Review columns in matches.csv
  review_status   accept   the match (rank 1) is right
                  correct  the right food is manual_fdc_id (any FNDDS fdc_id)
                  none     no FNDDS food fits
  manual_fdc_id   for `correct`
  review_note     free text

Recording twice is safe: identical events are skipped.

Usage
  python3 python/record_feedback.py --reviewer <name> [--dataset datasets/perls9]
"""
import argparse
import sys

import pandas as pd

from dietcali import config, fndds
from dietcali.feedback import append_events, events_from_review
from dietcali.pipeline import load_run


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default="datasets/perls9")
    ap.add_argument("--reviewer", required=True, help="who reviewed (stored with each event)")
    args = ap.parse_args(argv)

    ds = config.load_dataset(args.dataset)
    sheet = ds["match_dir"] / "matches.csv"
    if not sheet.exists():
        sys.exit(f"{sheet} not found; run python/fndds_match.py first")
    matches = pd.read_csv(sheet, dtype=str, keep_default_na=False)

    events, problems = [], []
    for run_id, part in matches.groupby("run_id"):          # candidates of the run each row came from
        run = load_run(ds["match_dir"], run_id)
        foods = fndds.load_foods(ds["fndds_dir"]) if ds["fndds_dir"] and ds["fndds_dir"].exists() else None
        ev, pr = events_from_review(part, run["candidates"], ds["name"], args.reviewer, foods)
        events += ev
        problems += pr

    n = append_events(ds["feedback_log"], events)
    reviewed = (matches["review_status"].str.strip() != "").sum()
    print(f"{reviewed} reviewed rows -> {len(events)} events, {n} new, written to "
          f"{ds['feedback_log'].relative_to(config.PROJECT_ROOT)}")
    for p in problems:
        print("  !", p)
    return events, problems


if __name__ == "__main__":
    main()
