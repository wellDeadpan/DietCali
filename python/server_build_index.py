"""
Server job: build the dense (FAISS) index for an FNDDS release + embedding model.

  python python/server_build_index.py                       # active release, active embedding model
  python python/server_build_index.py --release 2026-10-31  # a newly downloaded release (before activating)
  python python/server_build_index.py --model <name> [--register]   # try another embedding model
"""
import argparse

from dietcali.server import MatchService


def main(argv=None, service=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release")
    ap.add_argument("--model", help="embedding model (default: the active one)")
    ap.add_argument("--register", action="store_true", help="register --model in the model registry")
    args = ap.parse_args(argv)
    svc = service or MatchService()
    if args.model and args.register:
        svc.models.register("embedding", args.model, source="manual")
    d = svc.build_index(args.release, args.model)
    print(f"built index {d}")
    return d


if __name__ == "__main__":
    main()
