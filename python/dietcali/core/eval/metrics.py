"""Ranking metrics for a run against the gold set.

A candidate is correct if its food_code equals the gold food_code (stable
across FNDDS releases) or, when either code is missing, its fdc_id equals the
gold fdc_id.
"""
import pandas as pd

SOURCES = ["bm25", "dense", "api"]


def _is_gold(c, g) -> bool:
    if c["food_code"] and g["gold_food_code"]:
        return str(c["food_code"]) == str(g["gold_food_code"])
    return str(c["fdc_id"]) == str(g["gold_fdc_id"])


def gold_ranks(candidates: pd.DataFrame, gold: pd.DataFrame) -> pd.DataFrame:
    """one row per scored gold query: rank of the gold food in the run (NA if not shown),
    and whether each recall source found it"""
    scored = gold[gold["outcome"] != "none"]
    by_query = {k: g for k, g in candidates.groupby(["var", "search_term"])}
    rows = []
    for _, g in scored.iterrows():
        cands = by_query.get((g["var"], g["search_term"]))
        rank, found = pd.NA, {}
        if cands is not None:
            hits = [c for _, c in cands.iterrows() if _is_gold(c, g)]
            if hits:
                c = min(hits, key=lambda c: int(c["rank"]))
                rank = int(c["rank"])
                found = {s: str(c.get(f"{s}_rank", "")) not in ("", "nan", "<NA>", "None") for s in SOURCES}
        rows.append({"var": g["var"], "search_term": g["search_term"], "gold_rank": rank,
                     "in_run": cands is not None, **{f"found_{s}": found.get(s, False) for s in SOURCES}})
    return pd.DataFrame(rows)


def evaluate(candidates: pd.DataFrame, gold: pd.DataFrame, ks=(1, 3, 5), group: pd.Series = None) -> dict:
    """top-1 accuracy, recall@k (gold within the first k), MRR; optionally per group.

    group: optional Series indexed by var (e.g. food_group) for a per-group breakdown
    """
    r = gold_ranks(candidates, gold)
    r = r[r["in_run"]]

    def summarize(df):
        n = len(df)
        if n == 0:
            return {"n": 0}
        ranks = df["gold_rank"]
        out = {"n": n, "top1": float((ranks == 1).fillna(False).mean())}
        for k in ks:
            out[f"recall@{k}"] = float((ranks <= k).fillna(False).mean())
        out["mrr"] = float(ranks.map(lambda x: 0.0 if pd.isna(x) else 1.0 / x).mean())
        for s in SOURCES:
            if df[f"found_{s}"].any():
                out[f"found_by_{s}"] = float(df[f"found_{s}"].mean())
        return out

    result = {"overall": summarize(r),
              "not_scored_none": int((gold["outcome"] == "none").sum()),
              "gold_not_in_run": int((~gold_ranks(candidates, gold)["in_run"]).sum()) if len(gold) else 0}
    if group is not None and len(r):
        r = r.assign(group=r["var"].map(group).fillna(""))
        result["by_group"] = {g: summarize(df) for g, df in r.groupby("group")}
    return result
