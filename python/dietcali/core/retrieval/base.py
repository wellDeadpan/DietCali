from typing import TypedDict

import pandas as pd


class Hit(TypedDict):
    fdc_id: str
    food_code: str
    description: str
    wweia_category: str
    score: float


class LocalRetriever:
    """base for retrievers over the local FNDDS food table"""
    name = "local"
    version = ""

    def __init__(self, foods: pd.DataFrame):
        self.foods = foods

    def _hits(self, idx, scores) -> list:
        out = []
        for i, s in zip(idx, scores):
            f = self.foods.iloc[int(i)]
            out.append(Hit(fdc_id=f["fdc_id"], food_code=f["food_code"], description=f["description"],
                           wweia_category=f["wweia_category"], score=float(s)))
        return out

    def search(self, query: str, k: int) -> list:
        raise NotImplementedError
