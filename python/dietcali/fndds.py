"""Local FNDDS tables (FoodData Central "Survey (FNDDS)" CSV release)."""
import hashlib
from pathlib import Path

import pandas as pd


def _find(fndds_dir: Path, name: str) -> Path:
    hits = list(Path(fndds_dir).rglob(name))
    if not hits:
        raise FileNotFoundError(f"{name} not found under {fndds_dir}")
    return hits[0]


def load_foods(fndds_dir: Path) -> pd.DataFrame:
    """FNDDS foods: fdc_id, food_code, description, wweia_category (all str)"""
    food = pd.read_csv(_find(fndds_dir, "food.csv"), dtype=str)
    food = food[food["data_type"] == "survey_fndds_food"][["fdc_id", "description"]]
    survey = pd.read_csv(_find(fndds_dir, "survey_fndds_food.csv"), dtype=str)
    wweia_col = next((c for c in survey.columns if c.startswith("wweia")), None)
    survey = survey[["fdc_id", "food_code"] + ([wweia_col] if wweia_col else [])]
    out = food.merge(survey, on="fdc_id", how="left")

    cat_files = list(Path(fndds_dir).rglob("wweia_food_category.csv"))
    if wweia_col and cat_files:
        cats = pd.read_csv(cat_files[0], dtype=str)
        cats.columns = ["wweia_code", "wweia_category"] + list(cats.columns[2:])
        out = out.merge(cats[["wweia_code", "wweia_category"]], left_on=wweia_col, right_on="wweia_code", how="left")
    if "wweia_category" not in out:
        out["wweia_category"] = ""
    out = out[["fdc_id", "food_code", "description", "wweia_category"]].fillna("")
    return out.drop_duplicates("fdc_id").reset_index(drop=True)


def version_of(fndds_dir: Path, foods: pd.DataFrame) -> str:
    """release folder name + content hash of the food list"""
    h = hashlib.sha1("\n".join(foods["fdc_id"] + "\t" + foods["description"]).encode()).hexdigest()[:8]
    return f"{Path(fndds_dir).name}#{h}"
