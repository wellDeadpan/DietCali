"""Matcher: recall (several sources) -> RRF fusion -> rules -> optional rerank.

Queries are rows with var, search_term, exclude (+ optional form_label,
portion). The result is one row per candidate (CAND_COLS); best_matches()
turns it into one row per query with review flags.
"""
import pandas as pd

from .rerank.rules import excluded, head_ok, parse_exclude

SOURCES = ["bm25", "dense", "api"]
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
    def __init__(self, retrievers: list, reranker=None, k_retrieve: int = 50, top_k: int = 5, k_rrf: int = 60):
        if not retrievers:
            raise ValueError("at least one retriever is needed")
        self.retrievers = retrievers
        self.reranker = reranker
        self.k_retrieve = k_retrieve
        self.top_k = top_k
        self.k_rrf = k_rrf

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

    def components(self) -> dict:
        """versions of everything that determines the result (for run manifests)"""
        return {"retrievers": {r.name: r.version for r in self.retrievers},
                "reranker": {self.reranker.name: self.reranker.version} if self.reranker else None,
                "params": {"k_retrieve": self.k_retrieve, "top_k": self.top_k, "k_rrf": self.k_rrf}}


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
