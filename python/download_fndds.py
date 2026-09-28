"""
Download the FoodData Central "Survey (FNDDS)" CSV release and unzip it
under data_raw/fndds/.

Release selection
  --release YYYY-MM-DD   a specific release date
  --url URL              a specific zip URL (or file:// path)
  (default)              look for the newest release on the FDC download page;
                         fall back to FALLBACK_RELEASE if the page can't be read

Usage
  python3 python/download_fndds.py                 # newest release
  python3 python/download_fndds.py --release 2024-10-31
  python3 python/download_fndds.py --update-config # also set fndds_dir in config/paths.yml
  python3 python/download_fndds.py --list          # only show the releases found
"""
import argparse
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / ".here").exists())
DOWNLOAD_PAGE = "https://fdc.nal.usda.gov/download-datasets"
ZIP_URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_survey_food_csv_{release}.zip"
FALLBACK_RELEASE = "2024-10-31"
RELEASE_RE = re.compile(r"FoodData_Central_survey_food_csv_(\d{4}-\d{2}-\d{2})\.zip")
REQUIRED = ["food.csv", "survey_fndds_food.csv"]
HEADERS = {"User-Agent": "DietCali FNDDS downloader"}


def find_releases() -> list:
    """release dates listed on the FDC download page, newest first"""
    try:
        req = urllib.request.Request(DOWNLOAD_PAGE, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"could not read {DOWNLOAD_PAGE}: {e}")
        return []
    return sorted(set(RELEASE_RE.findall(html)), reverse=True)


def download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            pct = f" {done / total:5.1%}" if total else ""
            print(f"\r  {done / 1e6:7.1f} MB{pct}", end="", flush=True)
    print()
    tmp.replace(dest)


def extract(zip_path: Path, out_root: Path) -> Path:
    """unzip (the release zips hold one top-level folder) and return the folder that holds food.csv"""
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            sys.exit(f"corrupt file in zip: {bad}")
        tops = {n.split("/")[0] for n in z.namelist() if n.strip("/")}
        has_top_folder = len(tops) == 1 and any("/" in n for n in z.namelist())
        target = out_root / next(iter(tops)) if has_top_folder else out_root / zip_path.stem
        z.extractall(out_root if has_top_folder else target)
    hits = [p.parent for p in target.rglob("food.csv")]
    if not hits:
        sys.exit(f"food.csv not found in {zip_path.name}")
    folder = hits[0]
    missing = [f for f in REQUIRED if not (folder / f).exists()]
    if missing:
        sys.exit(f"{folder} is missing {missing}")
    return folder


def update_config(folder: Path) -> None:
    """set fndds_dir in config/paths.yml, keeping the rest of the file"""
    cfg = PROJECT_ROOT / "config" / "paths.yml"
    text = cfg.read_text()
    try:
        value = folder.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        value = folder.as_posix()
    line = f'fndds_dir: "{value}"'
    if re.search(r"(?m)^fndds_dir:.*$", text):
        text = re.sub(r"(?m)^fndds_dir:.*$", line, text)
    else:
        text = text.rstrip("\n") + (
            '\n\n# FoodData Central "Survey (FNDDS)" CSV download (unzipped folder)\n' + line + "\n")
    cfg.write_text(text)
    print(f"config/paths.yml: {line}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", help="release date, e.g. 2024-10-31")
    ap.add_argument("--url", help="zip URL (overrides --release)")
    ap.add_argument("--out", default="data_raw/fndds", help="download folder (relative to the project root)")
    ap.add_argument("--force", action="store_true", help="download again even if the zip exists")
    ap.add_argument("--keep-zip", action="store_true", help="keep the zip after extracting")
    ap.add_argument("--update-config", action="store_true", help="set fndds_dir in config/paths.yml")
    ap.add_argument("--list", action="store_true", help="list the releases on the download page and exit")
    args = ap.parse_args(argv)

    if args.list:
        releases = find_releases()
        print("\n".join(releases) if releases else "no releases found")
        return None

    if args.url:
        url = args.url
    else:
        release = args.release
        if not release:
            releases = find_releases()
            release = releases[0] if releases else FALLBACK_RELEASE
            print(f"release: {release}" + ("" if releases else " (fallback; download page not readable)"))
        url = ZIP_URL.format(release=release)

    out_root = Path(args.out) if Path(args.out).is_absolute() else PROJECT_ROOT / args.out
    out_root.mkdir(parents=True, exist_ok=True)
    zip_path = out_root / Path(url.split("?")[0]).name

    if zip_path.exists() and not args.force:
        print(f"using existing {zip_path.name}")
    else:
        print(f"downloading {url}")
        try:
            download(url, zip_path)
        except Exception as e:
            sys.exit(f"download failed: {e}\n"
                     f"check the release date on {DOWNLOAD_PAGE}, or pass --url")

    folder = extract(zip_path, out_root)
    if not args.keep_zip:
        zip_path.unlink()
    size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) / 1e6
    print(f"extracted to {folder} ({size:.0f} MB)")

    if args.update_config:
        update_config(folder)
    else:
        print(f'set in config/paths.yml:  fndds_dir: "{folder.relative_to(PROJECT_ROOT).as_posix()}"'
              if folder.is_relative_to(PROJECT_ROOT) else f"set fndds_dir to {folder}")
    return folder


if __name__ == "__main__":
    main()
