"""Matcher: recall (several sources) -> RRF fusion -> rules -> optional rerank.

Also writes a matching run: every run gets a run_id and its own folder with
the candidates that were shown, the chosen matches and a manifest recording
all component versions, so feedback can always be traced to what the
system showed at the time.

<match_dir>/
  matches.csv              review sheet for the latest run (review columns kept across runs)
  candidates.csv           latest run's candidates
  manifest.json            latest run's manifest
  runs/<run_id>/           candidates.csv, matches.csv, manifest.json (immutable history)
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path

import pandas as pd

from .config import PROJECT_ROOT
from .rerank.rules import excluded, head_ok, parse_exclude

SOURCES = ["bm25", "dense", "api"]
REVIEW_COLS = ["review_status", "manual_fdc_id", "review_note"]   # filled in by the reviewer
REVIEW_STATUSES = {"accept", "correct", "none"}
CAND_COLS = ["run_id", "var", "search_term", "rank", "fdc_id", "food_code", "description", "wweia_category",
             "rrf_score", "rerank_score", "head_ok"] + [f"{s}_{x}" for s in SOURCES for x in ("rank", "score")]


def rrf(rank_lists, k_rrf=60) -> dict:
    """reciprocal rank fusion: {doc: sum 1/(k + rank)}"""
    fused = {}
    for ranks in rank_lists:
        for r, doc in enumerate(ranks, start=1):
            fused[doc] = fused.get(doc, 0.0) + 1.0 / (k_rrf + r)
    return fused


class Matcher:
    def __init__(self, retrievers: list, reranker=None, k_retrieve: int = 50, top_k: int = 5, k_rrf: int = 60,
                 fndds_version: str = ""):
        if not retrievers:
            raise ValueError("at least one retriever is needed")
        self.retrievers = retrievers
        self.reranker = reranker
        self.k_retrieve = k_retrieve
        self.top_k = top_k
        self.k_rrf = k_rrf
        self.fndds_version = fndds_version

    @property
    def sources(self) -> list:
        return [r.name for r in self.retrievers]

    def match_query(self, query: str, exclude: str = "") -> list:
        """ranked candidates for one query (at most top_k)"""
        pool, ranks, scores, rank_lists = {}, {}, {}, []
        for ret in self.retrievers:
            hits = ret.search(query, self.k_retrieve)
            rank_lists.append([h["fdc_id"] for h in hits])
            for r, h in enumerate(hits, 1):
                d = h["fdc_id"]
                if d not in pool or (not pool[d]["food_code"] and h["food_code"]):
                    pool[d] = h                  # keep the record with the most information
                ranks.setdefault(d, {})[ret.name] = r
                scores.setdefault(d, {})[ret.name] = h["score"]
        fused = rrf(rank_lists, self.k_rrf)

        words = parse_exclude(exclude)
        kept = [d for d in fused if not excluded(pool[d]["description"], words)]
        rr = {}
        if self.reranker is not None and kept:
            rr = dict(zip(kept, self.reranker.score(query, [pool[d]["description"] for d in kept])))
        ordered = sorted(((d, head_ok(query, pool[d]["description"])) for d in kept),
                         key=lambda c: (not c[1], -rr.get(c[0], fused[c[0]])))

        out = []
        for rank, (d, hok) in enumerate(ordered[:self.top_k], 1):
            f = pool[d]
            row = {"rank": rank, "fdc_id": f["fdc_id"], "food_code": f["food_code"],
                   "description": f["description"], "wweia_category": f["wweia_category"],
                   "rrf_score": round(fused[d], 5), "rerank_score": round(rr[d], 4) if d in rr else None,
                   "head_ok": hok}
            for s in SOURCES:
                row[f"{s}_rank"] = ranks[d].get(s)
                row[f"{s}_score"] = round(scores[d][s], 3) if s in scores[d] else None
            out.append(row)
        return out

    def match(self, queries: pd.DataFrame, run_id: str = "") -> pd.DataFrame:
        """queries: var, search_term, exclude -> candidates (one row per candidate)"""
        rows = []
        for _, q in queries.iterrows():
            for c in self.match_query(q["search_term"], q.get("exclude", "")):
                rows.append({"run_id": run_id, "var": q["var"], "search_term": q["search_term"], **c})
        cand = pd.DataFrame(rows, columns=CAND_COLS)
        for s in SOURCES:
            cand[f"{s}_rank"] = cand[f"{s}_rank"].astype("Int64")
        return cand

    def manifest(self, run_id: str, dataset: str, food_items: Path) -> dict:
        return {
            "run_id": run_id,
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "dataset": dataset,
            "food_items_sha1": hashlib.sha1(Path(food_items).read_bytes()).hexdigest()[:12],
            "fndds_version": self.fndds_version,
            "retrievers": {r.name: r.version for r in self.retrievers},
            "reranker": {self.reranker.name: self.reranker.version} if self.reranker else None,
            "params": {"k_retrieve": self.k_retrieve, "top_k": self.top_k, "k_rrf": self.k_rrf},
            "code_version": git_commit(),
        }


def best_matches(queries: pd.DataFrame, cand: pd.DataFrame, sources: list) -> pd.DataFrame:
    """rank-1 candidate per (var, search_term) with review flags"""
    top = cand[cand["rank"] == 1].set_index(["var", "search_term"])
    n = cand.groupby(["var", "search_term"]).size()
    out = []
    for _, q in queries.iterrows():
        key = (q["var"], q["search_term"])
        row = {"var": q["var"], "search_term": q["search_term"],
               "form_label": q.get("form_label", ""), "portion": q.get("portion", "")}
        if key in top.index:
            t = top.loc[key]
            found = [s for s in sources if not pd.isna(t[f"{s}_rank"])]
            reasons = []
            if not t["head_ok"]:
                reasons.append("head word not in description")
            if len(sources) > 1 and len(found) < len(sources):
                reasons.append("not found by: " + ", ".join(s for s in sources if s not in found))
            if len(found) > 1 and max(t[f"{s}_rank"] for s in found) > 10:
                reasons.append("sources disagree")
            row.update({k: t[k] for k in ["run_id", "fdc_id", "food_code", "description", "wweia_category",
                                          "rrf_score", "rerank_score", "head_ok"]})
            row.update({f"{s}_rank": t[f"{s}_rank"] for s in SOURCES})
            row["n_candidates"] = int(n.get(key, 0))
            row["needs_review"] = bool(reasons)
            row["review_reason"] = "; ".join(reasons)
        else:
            row.update({"run_id": cand["run_id"].iloc[0] if len(cand) else "",
                        "n_candidates": 0, "needs_review": True, "review_reason": "no candidates"})
        out.append(row)
    return pd.DataFrame(out)


def carry_over_review(matches: pd.DataFrame, previous: Path) -> pd.DataFrame:
    """keep the reviewer's columns from the previous review sheet.
    `accept` refers to the food that was shown, so it is kept only if the
    chosen fdc_id is unchanged; corrections (manual_fdc_id) are always kept."""
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


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return out.stdout.strip() + ("+dirty" if dirty else "") if out.returncode == 0 else ""
    except Exception:
        return ""


def write_run(match_dir: Path, run_id: str, cand: pd.DataFrame, matches: pd.DataFrame, manifest: dict) -> Path:
    match_dir = Path(match_dir)
    run_dir = match_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    matches = carry_over_review(matches, match_dir / "matches.csv")
    for d in (run_dir, match_dir):
        cand.to_csv(d / "candidates.csv", index=False)
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    matches.drop(columns=REVIEW_COLS).to_csv(run_dir / "matches.csv", index=False)
    matches.to_csv(match_dir / "matches.csv", index=False)
    return run_dir


def load_run(match_dir: Path, run_id: str = "latest") -> dict:
    """candidates / matches / manifest of a run ('latest' = the current review sheet's run)"""
    match_dir = Path(match_dir)
    if run_id == "latest":
        run_id = json.loads((match_dir / "manifest.json").read_text())["run_id"]
    run_dir = match_dir / "runs" / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"run {run_id} not found in {match_dir / 'runs'}")
    return {
        "run_id": run_id,
        "dir": run_dir,
        "candidates": pd.read_csv(run_dir / "candidates.csv", dtype=str, keep_default_na=False),
        "matches": pd.read_csv(run_dir / "matches.csv", dtype=str, keep_default_na=False),
        "manifest": json.loads((run_dir / "manifest.json").read_text()),
    }
