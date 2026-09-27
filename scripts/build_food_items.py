"""
Build <dataset>/food_items.csv: the input for the USDA batch search.

  instrument questionnaire (q_id -> printed label, section, portion)
  + dataset var_map        (var -> q_id, item_type)
  + dataset dictionaries   (var -> label; used for validation)
  -> one row per food-frequency variable

Columns taken from the questionnaire / var_map are refreshed on every run.
The hand-maintained columns (search_terms, exclude, review, note) are kept
from the existing food_items.csv, matched by var. New food items get empty
search terms and review = 'check'.

Usage:  python3 scripts/build_food_items.py [datasets/perls9]
"""
import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
HAND_COLS = ["search_terms", "exclude", "review", "note"]
FORM_COLS = ["var", "dict_label", "q_id", "food_group", "form_label", "portion"]


def read_dict(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            var, label = line.split("=", 1)
            out[var.strip()] = " ".join(label.split())
    return out


def main(dataset_dir: str) -> None:
    ds = PROJECT_ROOT / dataset_dir
    cfg = yaml.safe_load((ds / "dataset.yml").read_text())
    p = lambda key: PROJECT_ROOT / cfg[key]

    questionnaire = pd.read_csv(PROJECT_ROOT / cfg["instrument_dir"] / "questionnaire.csv", dtype=str, keep_default_na=False)
    var_map = pd.read_csv(p("var_map"), dtype=str, keep_default_na=False)
    dict_vars = set().union(*(read_dict(PROJECT_ROOT / f) for f in cfg["dictionaries"].values()))

    # ---- validation
    errors = []
    missing = sorted(set(var_map["var"]) - dict_vars)
    if missing:
        errors.append(f"var_map variables not in any dictionary: {missing}")
    unmapped = sorted(dict_vars - set(var_map["var"]))
    if unmapped:
        errors.append(f"dictionary variables missing from var_map: {unmapped}")
    bad_q = sorted(set(var_map.loc[var_map["q_id"] != "", "q_id"]) - set(questionnaire["q_id"]))
    if bad_q:
        errors.append(f"var_map q_ids not in the questionnaire: {bad_q}")
    if errors:
        sys.exit("\n".join(errors))

    # ---- food-frequency items
    q = questionnaire.set_index("q_id")
    freq = var_map[(var_map["item_type"] == "frequency") & (var_map["role"] == "response")]
    not_freq = [v for v, qid in zip(freq["var"], freq["q_id"]) if q.at[qid, "response_type"] != "frequency"]
    if not_freq:
        sys.exit(f"item_type 'frequency' but the question is not a frequency question: {not_freq}")

    def form_label(qid):
        r = q.loc[qid]
        return r["item_label"] if not r["group_label"] else f"{r['group_label']}: {r['item_label']}"

    items = pd.DataFrame({
        "var": freq["var"].values,
        "dict_label": freq["dict_label"].values,
        "q_id": freq["q_id"].values,
        "food_group": [q.at[i, "section"] for i in freq["q_id"]],
        "form_label": [form_label(i) for i in freq["q_id"]],
        "portion": [q.at[i, "portion_text"] for i in freq["q_id"]],
    })

    # ---- keep hand-maintained columns
    out_path = p("food_items")
    if out_path.exists():
        old = pd.read_csv(out_path, dtype=str, keep_default_na=False)
        items = items.merge(old[["var"] + HAND_COLS], on="var", how="left")
        dropped = sorted(set(old["var"]) - set(items["var"]))
        if dropped:
            print(f"removed (no longer food-frequency items): {dropped}")
    for c in HAND_COLS:
        if c not in items:
            items[c] = ""
    items[HAND_COLS] = items[HAND_COLS].fillna("")
    new = items["search_terms"].str.strip() == ""
    items.loc[new, "review"] = "check"
    items.loc[new & (items["note"] == ""), "note"] = "no search terms yet"

    items[FORM_COLS + HAND_COLS].to_csv(out_path, index=False)
    print(f"wrote {out_path.relative_to(PROJECT_ROOT)}: {len(items)} food items, "
          f"{(items['review'] == 'check').sum()} flagged for review, {new.sum()} without search terms")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "datasets/perls9")
