"""DietCali: match dietary-assessment food items to FNDDS foods.

Layers
  core     pure logic, no paths or config: retrieval, rerank, matcher,
           feedback event schema, evaluation metrics
  server   one instance: FNDDS reference releases (update check, registry),
           offline indexes, model registry, feedback store, run records,
           and MatchService, the interface clients call
  client   one per study/dataset: reads its food items, calls the service,
           writes results + review sheet, submits review decisions

Clients never touch FNDDS files, indexes or models; they only talk to
MatchService (in-process today, HTTP later).
"""
