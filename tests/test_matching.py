"""End-to-end tests with a small mock FNDDS (no network, no models)."""
import json

import numpy as np
import pandas as pd
import pytest

from dietcali.eval import evaluate, gold_set
from dietcali.feedback import FeedbackEvent, append_events, events_from_review, latest_by_query, read_events
from dietcali.pipeline import Matcher, best_matches, carry_over_review, load_run, write_run
from dietcali.retrieval import BM25Retriever, DenseRetriever
from dietcali.text import head_word, tokenize

FOODS = pd.DataFrame(
    [("101", "11112110", "Milk, low fat (1%)", "Milk"),
     ("102", "11112210", "Milk, reduced fat (2%)", "Milk"),
     ("201", "14210000", "Cheese, cottage, NFS", "Cheese"),
     ("202", "14410000", "Cheese, ricotta", "Cheese"),
     ("301", "22600210", "Pork bacon, smoked or cured, cooked", "Bacon"),
     ("302", "24198700", "Bacon, turkey, cooked", "Bacon"),
     ("401", "92101000", "Coffee, brewed", "Coffee"),
     ("501", "58100000", "Soup, vegetable, canned", "Soups"),
     ("601", "41420000", "Tofu, raw", "Soy")],
    columns=["fdc_id", "food_code", "description", "wweia_category"])

QUERIES = pd.DataFrame([
    {"var": "milk2", "search_term": "low fat 1% milk", "exclude": "", "form_label": "Milk: 1 or 2%", "portion": "8 oz."},
    {"var": "cot.ch", "search_term": "cottage cheese", "exclude": "", "form_label": "Cottage or ricotta", "portion": "1/2 cup"},
    {"var": "cot.ch", "search_term": "ricotta cheese", "exclude": "", "form_label": "Cottage or ricotta", "portion": "1/2 cup"},
    {"var": "bacon", "search_term": "pork bacon", "exclude": "turkey", "form_label": "Bacon", "portion": "2 slices"},
    {"var": "coff", "search_term": "brewed coffee", "exclude": "", "form_label": "Coffee", "portion": "8 oz."},
    {"var": "kombu", "search_term": "kombucha", "exclude": "", "form_label": "Kombucha", "portion": ""},
])


def char_ngram_encoder(texts, dim=256):
    """stand-in for a sentence-transformers model"""
    out = np.zeros((len(texts), dim), "float32")
    for i, t in enumerate(texts):
        s = f"  {t.lower()}  "
        for j in range(len(s) - 2):
            out[i, hash(s[j:j + 3]) % dim] += 1
    return out


class FakeAPI:
    name, version = "api", "fake"

    def search(self, query, k):
        hits = FOODS[FOODS["description"].str.lower().str.contains(query.split()[-1])]
        return [{**r, "score": 100.0 - i} for i, r in enumerate(hits.to_dict("records"))][:k]


@pytest.fixture
def matcher():
    return Matcher([BM25Retriever(FOODS), DenseRetriever(FOODS, char_ngram_encoder, "char3"), FakeAPI()],
                   top_k=3, fndds_version="test#1")


def test_text():
    assert tokenize("Berries, boxes and beans") == ["berry", "box", "bean"]
    assert head_word("low fat 1% milk") == "milk"


def test_match_rules(matcher):
    cand = matcher.match(QUERIES, "r1")
    top = cand[cand["rank"] == 1].set_index("search_term")["description"]
    assert top["pork bacon"].startswith("Pork bacon")
    assert not cand[cand["search_term"] == "pork bacon"]["description"].str.contains("turkey").any()   # excluded
    assert top["cottage cheese"] == "Cheese, cottage, NFS"
    assert top["ricotta cheese"] == "Cheese, ricotta"                                    # one match per term
    assert cand.groupby("search_term").size().max() <= 3                                  # top_k
    m = best_matches(QUERIES, cand, matcher.sources)
    k = m.set_index("search_term").loc["kombucha"]          # dense always returns nearest foods ...
    assert k["needs_review"] and "head word not in description" in k["review_reason"]   # ... but flagged
    bm25_only = Matcher([BM25Retriever(FOODS)], top_k=3)
    m1 = best_matches(QUERIES, bm25_only.match(QUERIES, "r0"), bm25_only.sources)
    assert m1.set_index("search_term").loc["kombucha", "review_reason"] == "no candidates"


def review_and_record(tmp_path, matcher, statuses):
    cand = matcher.match(QUERIES, "r1")
    m = best_matches(QUERIES, cand, matcher.sources)
    write_run(tmp_path, "r1", cand, m, matcher.manifest("r1", "ds", _food_items(tmp_path)))
    sheet = pd.read_csv(tmp_path / "matches.csv", dtype=str, keep_default_na=False)
    for term, (status, manual) in statuses.items():
        i = sheet.index[sheet["search_term"] == term][0]
        sheet.loc[i, ["review_status", "manual_fdc_id"]] = [status, manual]
    sheet.to_csv(tmp_path / "matches.csv", index=False)
    run = load_run(tmp_path, "latest")
    events, problems = events_from_review(sheet, run["candidates"], "ds", "tester", FOODS)
    log = tmp_path / "events.jsonl"
    return log, append_events(log, events), events, problems


def _food_items(tmp_path):
    p = tmp_path / "food_items.csv"
    p.write_text("var,search_terms\n")
    return p


def test_write_run_and_manifest(tmp_path, matcher):
    cand = matcher.match(QUERIES, "r1")
    write_run(tmp_path, "r1", cand, best_matches(QUERIES, cand, matcher.sources),
              matcher.manifest("r1", "ds", _food_items(tmp_path)))
    man = json.loads((tmp_path / "runs" / "r1" / "manifest.json").read_text())
    assert man["retrievers"] == {"bm25": "bm25okapi", "dense": "char3", "api": "fake"}
    assert man["fndds_version"] == "test#1"
    assert load_run(tmp_path)["run_id"] == "r1"


def test_feedback_and_eval(tmp_path, matcher):
    log, n, events, problems = review_and_record(tmp_path, matcher, {
        "low fat 1% milk": ("accept", ""),
        "cottage cheese": ("correct", "202"),     # pretend ricotta is right: gold at a lower rank / elsewhere
        "brewed coffee": ("accept", ""),
        "kombucha": ("none", ""),
    })
    assert problems == [] and n == 4
    assert append_events(log, events) == 0                          # re-recording is a no-op
    rerun = [FeedbackEvent(**{**e.__dict__, "run_id": "r2", "event_id": "", "timestamp": "later"}) for e in events]
    assert append_events(log, rerun) == 0                           # same decision carried to a re-run
    ev = read_events(log)
    corr = next(e for e in ev if e.outcome == "correct")
    assert corr.selected["food_code"] == "14410000"                   # food_code stored
    assert len(corr.shown) == 3                                        # shown candidates kept (hard negatives)

    gold = gold_set(ev, "ds")
    assert set(gold["outcome"]) == {"accept", "correct", "none"}
    res = evaluate(load_run(tmp_path)["candidates"], gold)
    o = res["overall"]
    assert o["n"] == 3 and res["not_scored_none"] == 1
    assert o["top1"] == pytest.approx(2 / 3)                           # cottage cheese: gold not at rank 1
    assert o["recall@3"] >= o["top1"]


def test_gold_uses_food_code_across_releases(tmp_path, matcher):
    log, *_ = review_and_record(tmp_path, matcher, {"brewed coffee": ("accept", "")})
    gold = gold_set(read_events(log), "ds")
    # a new FNDDS release: same food_code, new fdc_id
    new = FOODS.assign(fdc_id=FOODS["fdc_id"].map(lambda x: "9" + x))
    cand = Matcher([BM25Retriever(new)], top_k=3).match(QUERIES, "r2")
    assert evaluate(cand, gold)["overall"]["top1"] == 1.0


def test_later_decision_supersedes():
    ctx = {"dataset": "ds", "var": "coff"}
    sel = {"fdc_id": "401", "food_code": "92101000", "description": "Coffee, brewed"}
    a = FeedbackEvent("brewed coffee", ctx, "accept", "expert", selected=sel, timestamp="2026-01-01T00:00:00")
    b = FeedbackEvent("brewed coffee", ctx, "none", "expert", timestamp="2026-02-01T00:00:00")
    u = FeedbackEvent("brewed coffee", ctx, "accept", "user", selected=sel, timestamp="2026-03-01T00:00:00")
    latest = latest_by_query([a, b, u])
    assert latest[("ds", "coff", "brewed coffee")].outcome == "none"   # user events ignored by default
    with pytest.raises(ValueError):
        FeedbackEvent("x", ctx, "accept", "expert")                     # accept needs a selected food


def test_review_carry_over(tmp_path, matcher):
    review_and_record(tmp_path, matcher, {"brewed coffee": ("accept", ""), "cottage cheese": ("correct", "202")})
    cand = matcher.match(QUERIES, "r2")
    m = best_matches(QUERIES, cand, matcher.sources)
    m.loc[m["search_term"] == "brewed coffee", "fdc_id"] = "999"        # top match changed in the new run
    m = carry_over_review(m, tmp_path / "matches.csv").set_index("search_term")
    assert m.loc["cottage cheese", "manual_fdc_id"] == "202" and m.loc["cottage cheese", "review_status"] == "correct"
    assert m.loc["brewed coffee", "review_status"] == ""
    assert "top match changed" in m.loc["brewed coffee", "review_note"]
