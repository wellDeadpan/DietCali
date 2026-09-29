"""
Server job: keep the FNDDS reference up to date.

  (no options)          check the FDC download page; download + register the newest
                        release if it is not registered yet. The very first release is
                        activated automatically; later ones are NOT - build the index,
                        evaluate (server_evaluate.py --release ...), then --activate.
  --status              show registered releases and the active one
  --check               only check whether a newer release is available
  --release DATE / --url URL      download a specific release
  --import-dir DIR --name NAME    copy an already downloaded + unzipped release into the server
                                  and register it (e.g. --name 2024-10-31)
  --activate NAME       make a registered release the active one

Run it by hand or from a scheduler (cron / Task Scheduler) - scheduling is not built in.
"""
import argparse
import json
from pathlib import Path

from dietcali.server import load_server_config
from dietcali.server.reference import FNDDSReference


def main(argv=None, cfg=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--release")
    ap.add_argument("--url")
    ap.add_argument("--import-dir")
    ap.add_argument("--name", help="release name for --import-dir / --url")
    ap.add_argument("--activate", metavar="NAME")
    args = ap.parse_args(argv)
    ref = FNDDSReference(cfg or load_server_config())

    if args.status:
        print(json.dumps({"active": ref.registry.active, "releases": ref.registry.entries}, indent=2))
        return
    if args.activate:
        ref.activate(args.activate)
        print(f"active FNDDS release: {args.activate} (rebuild the index if needed: server_build_index.py)")
        return
    if args.check:
        info = ref.check_update()
        print(json.dumps(info, indent=2))
        if not info["page_readable"]:
            print("download page not readable; check it by hand and use --release")
        return

    if args.import_dir:
        name = ref.import_dir(args.name or Path(args.import_dir).name, args.import_dir)
    elif args.release or args.url:
        name = ref.download(release=args.release, url=args.url)
    else:
        info = ref.check_update()
        if info["newest_available"] and not info["update_available"]:
            print(f"up to date: newest release {info['newest_available']} is registered (active: {info['active']})")
            return
        if not info["page_readable"]:
            print(f"download page not readable; trying fallback release {ref.cfg['fallback_release']}")
            if ref.cfg["fallback_release"] in ref.registry.entries:
                print("fallback release already registered")
                return
        name = ref.download(release=info["newest_available"])
    entry = ref.registry.entries[name]
    print(f"registered {name}: {entry['n_foods']} foods, content hash {entry['content_hash']}")
    if ref.registry.active is None:
        ref.activate(name)
        print(f"activated {name} (first release); next: python python/server_build_index.py")
    elif ref.registry.active != name:
        print(f"not activated (active: {ref.registry.active}). Next: server_build_index.py --release {name}, "
              f"server_evaluate.py --dataset <name> --release {name}, then --activate {name}")
    return name


if __name__ == "__main__":
    main()
