import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .base import Hit

FDC_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


class USDAAPIRetriever:
    """USDA FoodData Central search API, restricted to Survey (FNDDS).
    Responses are cached per query; failed queries are collected in `failed`
    and not cached, so they are retried on the next run."""
    name = "api"

    def __init__(self, api_key: str, cache_dir: Path = None, sleep_sec: float = 0.2, retries: int = 5):
        self.api_key = api_key
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.sleep_sec = sleep_sec
        self.retries = retries
        self.failed = []
        self.version = "fdc-search-v1 " + time.strftime("%Y-%m-%d")

    def _get(self, query: str, k: int) -> dict:
        params = {"api_key": self.api_key, "query": query, "dataType": "Survey (FNDDS)",
                  "pageSize": k, "pageNumber": 1}
        url = f"{FDC_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.retries - 1:
                    raise
            except urllib.error.URLError:
                if attempt == self.retries - 1:
                    raise
            time.sleep(min(2 ** attempt, 16))

    def search(self, query, k):
        cache = None
        if self.cache_dir is not None:
            h = hashlib.sha1(f"{query}|{k}".encode()).hexdigest()[:16]
            cache = self.cache_dir / f"{h}.json"
            if cache.exists():
                return json.loads(cache.read_text())
        try:
            time.sleep(self.sleep_sec)
            res = self._get(query, k)
        except Exception as e:
            self.failed.append((query, str(e)))
            return []
        hits = [Hit(fdc_id=str(f.get("fdcId", "")), food_code=str(f.get("foodCode", "") or ""),
                    description=f.get("description", ""), wweia_category=f.get("foodCategory", "") or "",
                    score=float(f.get("score", 0) or 0))
                for f in res.get("foods", [])]
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(hits))
        return hits
