"""Results received from the service, the review sheet, and turning review
decisions into feedback events."""
import json
from pathlib import Path

import pandas as pd

from ..core.feedback import FeedbackEvent

REVIEW_COLS = ["review_status", "manual_fdc_id", "review_note"]   # filled in by the reviewer
REVIEW_STATUSES = {"accept", "correct", "none"}


def write_results(results_dir: Path, run: dict, matches: pd.DataFrame) -> Path:
    """store a service result: runs/<run_id>/ copy + review sheet (review columns carried over)"""
    results_dir = Path(results_dir)
    run_dir = results_dir / "runs" / run["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    matches = carry_over_review(matches, results_dir / "matches.csv")
    for d in (run_dir, results_dir):
        run["candidates"].to_csv(d / "candidates.csv", index=False)
        (d / "manifest.json").write_text(json.dumps(run["manifest"], indent=2))
    matches.drop(columns=REVIEW_COLS).to_csv(run_dir / "matches.csv", index=False)
    matches.to_csv(results_dir / "matches.csv", index=False)
    return run_dir


def load_results(results_dir: Path, run_id: str) -> dict:
    d = Path(results_dir) / "runs" / run_id
    if not d.exists():
        raise FileNotFoundError(f"run {run_id} not found in {Path(results_dir) / 'runs'}")
    return {"run_id": run_id, "manifest": json.loads((d / "manifest.json").read_text()),
            "candidates": pd.read_csv(d / "candidates.csv", dtype=str, keep_default_na=False)}


def carry_over_review(matches: pd.DataFrame, previous: Path) -> pd.DataFrame:
    """keep the reviewer's columns from the previous review sheet.
    `accept` refers to the food that was shown, so it is kept only if the
    chosen fdc_id is unchanged; corrections (manual_fdc_id) are always kept."""
    matches = matches.copy()
    for c in REVIEW_COLS:
        matches[c] = ""
    if not Path(previous).exists():
        return matches
    old = pd.read_csv(previous, dtype=str, keep_default_na=False)
    if not set(REVIEW_COLS) <= set(old.columns):
        return matches
    old = old.set_index(["var", "search_term"])
    for i, r in matches.iterrows():
        key = (r["var"], r["search_term"])
        if key not in old.index:
            continue
        o = old.loc[key]
        matches.at[i, "manual_fdc_id"] = o["manual_fdc_id"]
        matches.at[i, "review_note"] = o["review_note"]
        status = o["review_status"]
        if status == "accept" and str(o.get("fdc_id", "")) != str(r.get("fdc_id", "")):
            matches.at[i, "review_note"] = "; ".join(x for x in [o["review_note"], "top match changed since review"] if x)
            status = ""
        matches.at[i, "review_status"] = status
    return matches


def _food(row) -> dict:
    return {"fdc_id": str(row["fdc_id"]), "food_code": str(row.get("food_code", "") or ""),
            "description": str(row.get("description", "") or "")}


def events_from_review(sheet: pd.DataFrame, candidates: pd.DataFrame, dataset: str, reviewer: str = "",
                       lookup_foods=None, excludes: dict = None) -> tuple:
    """review sheet rows (one run) -> (events, problems)

    review_status  accept   the rank-1 match is right
                   correct  manual_fdc_id is right (any FNDDS food; resolved with lookup_foods)
                   none     no FNDDS food fits
    lookup_foods   callable fdc_ids -> DataFrame (MatchService.lookup_foods) for corrections
    excludes       {(var, search_term): exclude words}, stored in the event context
    """
    events, problems = [], []
    by_query = {k: g.sort_values("rank", key=lambda s: s.astype(int))
                for k, g in candidates.groupby(["var", "search_term"])}
    wanted = [str(x).strip() for x in sheet.loc[sheet["review_status"].str.strip() == "correct", "manual_fdc_id"]]
    found = lookup_foods([w for w in wanted if w]).set_index("fdc_id") if lookup_foods and any(wanted) else None
    for _, m in sheet.iterrows():
        status = str(m.get("review_status", "")).strip().lower()
        if not status:
            continue
        key = (m["var"], m["search_term"])
        shown_df = by_query.get(key, pd.DataFrame(columns=candidates.columns))
        shown = [{"rank": int(r["rank"]), **_food(r)} for _, r in shown_df.iterrows()]
        context = {"dataset": dataset, "var": m["var"], "form_label": m.get("form_label", ""),
                   "portion": m.get("portion", ""), "exclude": (excludes or {}).get(key, "")}
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
            elif found is not None and fid in found.index:
                selected = _food({"fdc_id": fid, **found.loc[fid].to_dict()})
            else:
                problems.append(f"{key}: manual_fdc_id {fid} is not an FNDDS food in the active release")
                continue
        elif status not in REVIEW_STATUSES:
            problems.append(f"{key}: unknown review_status {status!r} (use accept / correct / none)")
            continue
        events.append(FeedbackEvent(query=m["search_term"], context=context, outcome=status,
                                    label_source="expert", run_id=str(m.get("run_id", "")), shown=shown,
                                    selected=selected, reviewer=reviewer, note=str(m.get("review_note", ""))))
    return events, problems
