"""Turn a filled-in review sheet (matches.csv) into feedback events."""
import pandas as pd

from .schema import FeedbackEvent


def _food(row) -> dict:
    return {"fdc_id": str(row["fdc_id"]), "food_code": str(row.get("food_code", "") or ""),
            "description": str(row.get("description", "") or "")}


def events_from_review(matches: pd.DataFrame, candidates: pd.DataFrame, dataset: str, reviewer: str = "",
                       foods: pd.DataFrame = None) -> tuple:
    """-> (events, problems)

    review_status  accept   the rank-1 match is right
                   correct  manual_fdc_id is right (from the candidates, or any FNDDS food if `foods` given)
                   none     no FNDDS food fits
    """
    events, problems = [], []
    by_query = {k: g.sort_values("rank", key=lambda s: s.astype(int))
                for k, g in candidates.groupby(["var", "search_term"])}
    lookup = foods.set_index("fdc_id") if foods is not None else None
    for _, m in matches.iterrows():
        status = str(m.get("review_status", "")).strip().lower()
        if not status:
            continue
        key = (m["var"], m["search_term"])
        shown_df = by_query.get(key, pd.DataFrame(columns=candidates.columns))
        shown = [{"rank": int(r["rank"]), **_food(r)} for _, r in shown_df.iterrows()]
        context = {"dataset": dataset, "var": m["var"], "form_label": m.get("form_label", ""),
                   "portion": m.get("portion", "")}
        selected = None
        if status == "accept":
            if not shown:
                problems.append(f"{key}: accept but no candidates")
                continue
            selected = {k: shown[0][k] for k in ("fdc_id", "food_code", "description")}
        elif status == "correct":
            fid = str(m.get("manual_fdc_id", "")).strip()
            if not fid:
                problems.append(f"{key}: correct but manual_fdc_id is empty")
                continue
            hit = next((s for s in shown if s["fdc_id"] == fid), None)
            if hit:
                selected = {k: hit[k] for k in ("fdc_id", "food_code", "description")}
            elif lookup is not None and fid in lookup.index:
                selected = _food({"fdc_id": fid, **lookup.loc[fid].to_dict()})
            else:
                selected = {"fdc_id": fid, "food_code": "", "description": ""}
                problems.append(f"{key}: manual_fdc_id {fid} not among candidates; food_code unknown")
        elif status != "none":
            problems.append(f"{key}: unknown review_status {status!r} (use accept / correct / none)")
            continue
        events.append(FeedbackEvent(query=m["search_term"], context=context, outcome=status,
                                    label_source="expert", run_id=str(m.get("run_id", "")), shown=shown,
                                    selected=selected, reviewer=reviewer, note=str(m.get("review_note", ""))))
    return events, problems
