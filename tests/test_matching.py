"""Tests for the core / server / client layers with a small mock FNDDS
(no network, no models: a char-n-gram encoder stands in for sentence-transformers)."""
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from dietcali.client import events_from_review, load_results, write_results
from dietcali.client.review import carry_over_review
from dietcali.core.eval import evaluate, gold_set
from dietcali.core.feedback import FeedbackEvent, latest_by_query
from dietcali.core.matcher import Matcher, best_matches
from dietcali.core.retrieval import BM25Retriever, DenseRetriever, normalize
from dietcali.core.text import head_word, tokenize
from dietcali.server import MatchService, load_server_config

FOODS = [("101", "11112110", "Milk, low fat (1%)"), ("102", "11112210", "Milk, reduced fat (2%)"),
         ("201", "14210000", "Cheese, cottage, NFS"), ("202", "14410000", "Cheese, ricotta"),
         ("301", "22600210", "Pork bacon, smoked or cured, cooked"), ("302", "24198700", "Bacon, turkey, cooked"),
         ("401", "92101000", "Coffee, brewed"), ("501", "58100000", "Soup, vegetable, canned"),
         ("601", "41420000", "Tofu, raw")]

QUERIES = pd.DataFrame([
    {"var": "milk2", "search_term": "low fat 1% milk", "exclude": "", "form_label": "1 or 2% milk", "portion": "8 oz."},
    {"var": "cot.ch", "search_term": "cottage cheese", "exclude": "", "form_label": "Cottage or ricotta", "portion": "1/2 cup"},
    {"var": "cot.ch", "search_term": "ricotta cheese", "exclude": "", "form_label": "Cottage or ricotta", "portion": "1/2 cup"},
    {"var": "bacon", "search_term": "pork bacon", "exclude": "turkey", "form_label": "Bacon", "portion": "2 slices"},
    {"var": "coff", "search_term": "brewed coffee", "exclude": "", "form_label": "Coffee", "portion": "8 oz."},
    {"var": "kombu", "search_term": "kombucha", "exclude": "", "form_label": "Kombucha", "portion": ""},
])


def encoder(texts, dim=256):
    out = np.zeros((len(texts), dim), "float32")
    for i, t in enumerate(texts):
        s = f"  {t.lower()}  "
        for j in range(len(s) - 2):
            out[i, hash(s[j:j + 3]) % dim] += 1
    return out


def foods_df(fdc_prefix=""):
    return pd.DataFrame([(fdc_prefix + f, c, d, "") for f, c, d in FOODS],
                        columns=["fdc_id", "food_code", "description", "wweia_category"])


def write_release(folder, fdc_prefix=""):
    """FNDDS CSV release layout: food.csv + survey_fndds_food.csv"""
    folder.mkdir(parents=True, exist_ok=True)
    f = foods_df(fdc_prefix)
    pd.DataFrame({"fdc_id": f["fdc_id"], "data_type": "survey_fndds_food", "description": f["description"],
                  "food_category_id": "", "publication_date": ""}).to_csv(folder / "food.csv", index=False)
    pd.DataFrame({"fdc_id": f["fdc_id"], "food_code": f["food_code"], "wweia_category_number": "",
                  "start_date": "", "end_date": ""}).to_csv(folder / "survey_fndds_food.csv", index=False)
    return folder


class FakeReranker:
    name, version = "cross_encoder", "fake"

    def __init__(self, model_name):
        self.version = model_name

    def score(self, query, docs):
        q = set(tokenize(query))
        return [len(q & set(tokenize(d))) for d in docs]


@pytest.fixture
def server(tmp_path):
    """a server with one active release and its index"""
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "config" / "server.yml").write_text(
        "server_dir: server\nfndds: {download_page: 'http://localhost:1/none', zip_url: 'file:///none/{release}.zip', "
        "fallback_release: '2024-10-31'}\nmodels: {embedding: char3, reranker: fake-ce}\n"
        "matching: {sources: [bm25, dense], rerank: false, k_retrieve: 50, top_k: 3}\n")
    cfg = load_server_config(root / "config" / "server.yml", root=root)
    svc = MatchService(cfg, encoder_factory=lambda m: encoder, reranker_factory=FakeReranker)
    svc.reference.register("r2024", write_release(tmp_path / "dl" / "r2024"))
    svc.reference.activate("r2024")
    svc.build_index()
    return svc


# ---------------------------------------------------------------- core
def test_text():
    assert tokenize("Berries, boxes and beans") == ["berry", "box", "bean"]
    assert head_word("low fat 1% milk") == "milk"


def test_matcher_rules():
    f = foods_df()
    m = Matcher([BM25Retriever(f), DenseRetriever(f, normalize(encoder(f["description"].tolist())), encoder, "char3")],
                top_k=3)
    cand = m.match(QUERIES, "r1")
    top = cand[cand["rank"] == 1].set_index("search_term")["description"]
    assert top["pork bacon"].startswith("Pork bacon")
    assert not cand[cand["search_term"] == "pork bacon"]["description"].str.contains("turkey").any()
    assert top["cottage cheese"] == "Cheese, cottage, NFS" and top["ricotta cheese"] == "Cheese, ricotta"
    k = best_matches(QUERIES, cand, m.sources).set_index("search_term").loc["kombucha"]
    assert k["needs_review"] and "head word not in description" in k["review_reason"]   # dense always returns something
    bm = Matcher([BM25Retriever(f)], top_k=3)
    assert best_matches(QUERIES, bm.match(QUERIES, "r0"), bm.sources).set_index("search_term").loc[
        "kombucha", "review_reason"] == "no candidates"


def test_feedback_schema():
    ctx = {"dataset": "ds", "var": "coff"}
    sel = {"fdc_id": "401", "food_code": "92101000", "description": "Coffee, brewed"}
    a = FeedbackEvent("brewed coffee", ctx, "accept", "expert", run_id="r1", selected=sel, timestamp="2026-01-01")
    b = FeedbackEvent("brewed coffee", ctx, "none", "expert", timestamp="2026-02-01")
    u = FeedbackEvent("brewed coffee", ctx, "accept", "user", selected=sel, timestamp="2026-03-01")
    assert latest_by_query([a, b, u])[("ds", "coff", "brewed coffee")].outcome == "none"   # user labels ignored
    assert FeedbackEvent("brewed coffee", ctx, "accept", "expert", run_id="r2", selected=sel).event_id == a.event_id
    with pytest.raises(ValueError):
        FeedbackEvent("x", ctx, "accept", "expert")


# ---------------------------------------------------------------- server
def test_reference_registry_and_versions(server, tmp_path):
    ref = server.reference
    assert ref.active() == "r2024" and ref.version().startswith("r2024#")
    ref.register("r2026", write_release(tmp_path / "dl" / "r2026", fdc_prefix="9"))
    assert ref.active() == "r2024"                                   # new release not activated automatically
    assert set(json.loads((server.cfg["dirs"]["fndds"] / "registry.json").read_text())["entries"]) == {"r2024", "r2026"}
    assert server.models.active("embedding") == "char3"              # defaults registered


def test_download_from_zip(server, tmp_path):
    src = write_release(tmp_path / "zipsrc" / "FoodData_Central_survey_food_csv_2099-01-01")
    zpath = tmp_path / "FoodData_Central_survey_food_csv_2099-01-01.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for f in src.iterdir():
            z.write(f, f"{src.name}/{f.name}")
    name = server.reference.download(url=zpath.as_uri(), progress=lambda *a: None)
    assert name == "2099-01-01"                                                    # named by release date
    assert (server.cfg["dirs"]["fndds"] / name / "food.csv").exists()               # no nested folder
    assert server.reference.registry.entries[name]["n_foods"] == len(FOODS)
    imported = server.reference.import_dir("copy", src.parent)                     # existing download
    assert (server.cfg["dirs"]["fndds"] / imported / "food.csv").exists()


def test_service_match_stores_run(server):
    run = server.match(QUERIES, "ds")
    man = run["manifest"]
    assert man["request"]["dataset"] == "ds" and man["fndds_version"] == server.reference.version()
    assert man["retrievers"] == {"bm25": "bm25okapi", "dense": "char3"}
    assert (server.cfg["dirs"]["runs"] / run["run_id"] / "candidates.csv").exists()
    reranked = server.match(QUERIES, "ds", rerank=True)
    assert reranked["manifest"]["reranker"] == {"cross_encoder": "fake-ce"}


def test_stale_index_is_refused(server, tmp_path):
    server.reference.register("r2024", write_release(tmp_path / "dl" / "r2024b", fdc_prefix="7"))   # content changed
    with pytest.raises(RuntimeError, match="out of date"):
        MatchService(server.cfg, encoder_factory=lambda m: encoder).match(QUERIES, "ds")


# ---------------------------------------------------------------- client <-> server
def review(server, tmp_path, statuses):
    results = tmp_path / "ds" / "fndds_match"
    run = server.match(QUERIES, "ds")
    write_results(results, run, best_matches(QUERIES, run["candidates"], run["manifest"]["request"]["sources"]))
    sheet = pd.read_csv(results / "matches.csv", dtype=str, keep_default_na=False)
    for term, (status, manual) in statuses.items():
        i = sheet.index[sheet["search_term"] == term][0]
        sheet.loc[i, ["review_status", "manual_fdc_id"]] = [status, manual]
    sheet.to_csv(results / "matches.csv", index=False)
    excludes = dict(zip(zip(QUERIES["var"], QUERIES["search_term"]), QUERIES["exclude"]))
    events, problems = events_from_review(sheet, load_results(results, run["run_id"])["candidates"], "ds", "tester",
                                          lookup_foods=server.lookup_foods, excludes=excludes)
    return run, results, events, problems


def test_feedback_and_evaluation(server, tmp_path):
    run, _, events, problems = review(server, tmp_path, {
        "low fat 1% milk": ("accept", ""), "cottage cheese": ("correct", "202"),
        "brewed coffee": ("accept", ""), "kombucha": ("none", ""), "pork bacon": ("correct", "999999")})
    assert problems == ["('bacon', 'pork bacon'): manual_fdc_id 999999 is not an FNDDS food in the active release"]
    assert server.record_feedback(events) == 4
    assert server.record_feedback(events) == 0                                     # idempotent
    stored = server.feedback.read()
    corr = next(e for e in stored if e.outcome == "correct")
    assert corr.selected["food_code"] == "14410000" and len(corr.shown) == 3        # food_code + hard negatives
    assert server.cfg["dirs"]["feedback"].exists()                                  # stored on the server side

    res = server.evaluate_run(run["run_id"])
    assert res["overall"]["n"] == 3 and res["not_scored_none"] == 1
    assert res["overall"]["top1"] == pytest.approx(2 / 3)                          # cottage cheese: gold not rank 1
    assert (server.cfg["dirs"]["runs"] / run["run_id"] / "eval.json").exists()


def test_evaluate_new_release_before_activation(server, tmp_path):
    _, _, events, _ = review(server, tmp_path, {"brewed coffee": ("accept", ""), "low fat 1% milk": ("accept", "")})
    server.record_feedback(events)
    server.reference.register("r2026", write_release(tmp_path / "dl" / "r2026", fdc_prefix="9"))  # new fdc_ids
    server.build_index(release="r2026")
    res = server.evaluate_config("ds", release="r2026")
    assert res["manifest"]["fndds_version"].startswith("r2026") and res["overall"]["top1"] == 1.0   # via food_code
    assert server.reference.active() == "r2024"


def test_review_carry_over(server, tmp_path):
    run, results, _, _ = review(server, tmp_path, {"brewed coffee": ("accept", ""), "cottage cheese": ("correct", "202")})
    m = best_matches(QUERIES, run["candidates"], ["bm25", "dense"])
    m.loc[m["search_term"] == "brewed coffee", "fdc_id"] = "999"                  # top match changed in a new run
    m = carry_over_review(m, results / "matches.csv").set_index("search_term")
    assert m.loc["cottage cheese", "review_status"] == "correct" and m.loc["cottage cheese", "manual_fdc_id"] == "202"
    assert m.loc["brewed coffee", "review_status"] == "" and "top match changed" in m.loc["brewed coffee", "review_note"]
