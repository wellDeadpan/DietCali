"""FNDDS reference releases: find, download, register, activate.

A new release is downloaded and registered but NOT activated automatically:
build its index, evaluate it against the feedback gold set, then activate.
"""
import hashlib
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from .registry import Registry

RELEASE_RE = re.compile(r"FoodData_Central_survey_food_csv_(\d{4}-\d{2}-\d{2})\.zip")
REQUIRED = ["food.csv", "survey_fndds_food.csv"]
HEADERS = {"User-Agent": "DietCali FNDDS reference updater"}


class FNDDSReference:
    def __init__(self, cfg: dict):
        self.cfg = cfg["fndds"]
        self.dir = cfg["dirs"]["fndds"]
        self.registry = Registry(self.dir / "registry.json")

    # ---------------- discovery / download
    def available_releases(self) -> list:
        """release dates listed on the FDC download page, newest first ([] if unreadable)"""
        try:
            req = urllib.request.Request(self.cfg["download_page"], headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", errors="replace")
        except Exception:
            return []
        return sorted(set(RELEASE_RE.findall(html)), reverse=True)

    def check_update(self) -> dict:
        """newest release on the download page vs the registered / active ones"""
        avail = self.available_releases()
        newest = avail[0] if avail else None
        return {"newest_available": newest, "page_readable": bool(avail),
                "registered": sorted(self.registry.entries), "active": self.registry.active,
                "update_available": bool(newest and newest not in self.registry.entries)}

    def download(self, release: str = None, url: str = None, progress=print) -> str:
        """download + extract + register a release; returns the release name (its date when known)"""
        if not url:
            if not release:
                avail = self.available_releases()
                release = avail[0] if avail else self.cfg["fallback_release"]
            url = self.cfg["zip_url"].format(release=release)
        zip_name = Path(url.split("?")[0]).name
        m = RELEASE_RE.search(zip_name)
        name = release or (m.group(1) if m else Path(zip_name).stem)
        self.dir.mkdir(parents=True, exist_ok=True)
        zip_path = self.dir / zip_name
        progress(f"downloading {url}")
        _download(url, zip_path, progress)
        folder = _extract(zip_path, self.dir / name)
        zip_path.unlink()
        return self.register(name, folder, source=url)

    def import_dir(self, name: str, src: Path) -> str:
        """copy an already downloaded + unzipped release into the server and register it"""
        src = Path(src)
        hits = [p.parent for p in src.rglob("food.csv")]
        if not hits:
            raise FileNotFoundError(f"food.csv not found under {src}")
        target = self.dir / name
        if target.exists():
            raise FileExistsError(f"{target} exists; choose another --name")
        shutil.copytree(hits[0], target)
        return self.register(name, target, source=f"import:{src}")

    def register(self, name: str, folder: Path, source: str = "") -> str:
        """register an extracted release folder (also used to import an existing download)"""
        folder = Path(folder)
        missing = [f for f in REQUIRED if not (folder / f).exists()]
        if missing:
            raise FileNotFoundError(f"{folder} is missing {missing}")
        foods = load_foods(folder)
        self.registry.register(name, path=str(folder), source=source, n_foods=len(foods),
                               content_hash=content_hash(foods), downloaded=time.strftime("%Y-%m-%dT%H:%M:%S"))
        return name

    # ---------------- use
    def activate(self, name: str):
        self.registry.activate(name)

    def active(self) -> str:
        if not self.registry.active:
            raise RuntimeError("no active FNDDS release; run python/server_update_fndds.py")
        return self.registry.active

    def folder(self, name: str = None) -> Path:
        return Path(self.registry.entries[name or self.active()]["path"])

    def foods(self, name: str = None) -> pd.DataFrame:
        return load_foods(self.folder(name))

    def version(self, name: str = None) -> str:
        name = name or self.active()
        return f"{name}#{self.registry.entries[name]['content_hash']}"


def load_foods(folder: Path) -> pd.DataFrame:
    """FNDDS foods: fdc_id, food_code, description, wweia_category (all str)"""
    folder = Path(folder)
    food = pd.read_csv(folder / "food.csv", dtype=str)
    food = food[food["data_type"] == "survey_fndds_food"][["fdc_id", "description"]]
    survey = pd.read_csv(folder / "survey_fndds_food.csv", dtype=str)
    wweia_col = next((c for c in survey.columns if c.startswith("wweia")), None)
    survey = survey[["fdc_id", "food_code"] + ([wweia_col] if wweia_col else [])]
    out = food.merge(survey, on="fdc_id", how="left")
    cat_file = folder / "wweia_food_category.csv"
    if wweia_col and cat_file.exists():
        cats = pd.read_csv(cat_file, dtype=str)
        cats.columns = ["wweia_code", "wweia_category"] + list(cats.columns[2:])
        out = out.merge(cats[["wweia_code", "wweia_category"]], left_on=wweia_col, right_on="wweia_code", how="left")
    if "wweia_category" not in out:
        out["wweia_category"] = ""
    out = out[["fdc_id", "food_code", "description", "wweia_category"]].fillna("")
    return out.drop_duplicates("fdc_id").reset_index(drop=True)


def content_hash(foods: pd.DataFrame) -> str:
    return hashlib.sha1("\n".join(foods["fdc_id"] + "\t" + foods["description"]).encode()).hexdigest()[:8]


def _download(url: str, dest: Path, progress=print) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    progress(f"  {dest.stat().st_size / 1e6:.1f} MB")


def _extract(zip_path: Path, target: Path) -> Path:
    """unzip into `target` (dropping the zip's single top-level folder) and return target"""
    target = Path(target)
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"corrupt file in zip: {bad}")
        names = [n for n in z.namelist() if n.strip("/")]
        tops = {n.split("/")[0] for n in names}
        strip = len(tops) == 1 and all("/" in n for n in names if not n.endswith("/"))
        target.mkdir(parents=True, exist_ok=True)
        for info in z.infolist():
            rel = info.filename.split("/", 1)[1] if strip and "/" in info.filename else info.filename
            if not rel or info.is_dir():
                continue
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    if not (target / "food.csv").exists():
        hits = [p.parent for p in target.rglob("food.csv")]
        if not hits:
            raise FileNotFoundError(f"food.csv not found in {zip_path.name}")
        return hits[0]
    return target
