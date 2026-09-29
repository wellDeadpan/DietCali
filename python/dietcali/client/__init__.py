"""Client layer (one per study / dataset).

Knows only its own dataset (food_items.csv) and where to put results; all
FNDDS data, indexes, models and feedback storage are behind MatchService.

<dataset>/fndds_match/
  matches.csv              review sheet for the latest run (review columns kept across runs)
  candidates.csv           latest run's candidates
  manifest.json            latest run's manifest (as returned by the service)
  runs/<run_id>/           copy of every result received
"""
from .dataset import load_dataset, load_queries
from .review import REVIEW_COLS, events_from_review, load_results, write_results

__all__ = ["load_dataset", "load_queries", "REVIEW_COLS", "events_from_review", "load_results", "write_results"]
