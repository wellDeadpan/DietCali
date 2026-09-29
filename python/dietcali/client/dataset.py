from pathlib import Path

import pandas as pd
import yaml

from ..paths import PROJECT_ROOT, resolve


def load_dataset(dataset_dir: str, root: Path = PROJECT_ROOT) -> dict:
    """<dataset>/dataset.yml: name, food_items, results_dir (nothing server-side)"""
    ds_dir = resolve(dataset_dir, root)
    ds = yaml.safe_load((ds_dir / "dataset.yml").read_text()) or {}
    return {
        "name": ds.get("name", ds_dir.name),
        "dir": ds_dir,
        "food_items": resolve(ds["food_items"], root),
        "results_dir": resolve(ds.get("fndds_match_dir", ds_dir / "fndds_match"), root),
    }


def load_queries(food_items: Path) -> pd.DataFrame:
    """food_items.csv -> one query per (var, search_term)"""
    fi = pd.read_csv(food_items, dtype=str, keep_default_na=False)
    rows = [{"var": r["var"], "search_term": t.strip(), "exclude": r["exclude"],
             "form_label": r["form_label"], "portion": r["portion"]}
            for _, r in fi.iterrows() for t in r["search_terms"].split(";") if t.strip()]
    if not rows:
        raise ValueError(f"no search terms in {food_items}")
    return pd.DataFrame(rows)
