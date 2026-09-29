"""Server layer: reference data, indexes, models, feedback and the MatchService.

<server_dir>/
  reference/fndds/<release>/     FNDDS CSV releases
  reference/fndds/registry.json  downloaded releases + which one is active
  indexes/<release>/<model>/     offline index: food table + normalized embeddings
  models/registry.json           embedding / reranker models + which are active
  feedback/events.jsonl          feedback events from all datasets
  runs/<run_id>/                 manifest + candidates of every match request
  cache/usda_api_search/         cached USDA API responses
"""
from .config import load_server_config
from .service import MatchService

__all__ = ["load_server_config", "MatchService"]
