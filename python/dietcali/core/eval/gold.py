import pandas as pd

from ..feedback import latest_by_query


def gold_set(events: list, dataset: str, label_sources=("expert",)) -> pd.DataFrame:
    """latest decision per query -> var, search_term, gold_fdc_id, gold_food_code, outcome.
    outcome 'none' rows have no gold food (no FNDDS food fits); they are kept so
    they can be reported, but they are not scored."""
    rows = []
    for (ds, var, query), e in latest_by_query(events, label_sources).items():
        if ds != dataset:
            continue
        sel = e.selected or {}
        rows.append({"var": var, "search_term": query, "outcome": e.outcome,
                     "gold_fdc_id": sel.get("fdc_id", ""), "gold_food_code": sel.get("food_code", ""),
                     "gold_description": sel.get("description", ""), "label_run_id": e.run_id,
                     "label_time": e.timestamp})
    return pd.DataFrame(rows, columns=["var", "search_term", "outcome", "gold_fdc_id", "gold_food_code",
                                       "gold_description", "label_run_id", "label_time"])
