"""DietCali: match dietary-assessment food items to FNDDS foods.

Subpackages
  retrieval   recall sources: local BM25, local dense (FAISS), USDA search API
  rerank      exclusion / head-word rules and the optional cross-encoder
  feedback    feedback event schema and log (expert review, user choices)
  eval        gold set from feedback + ranking metrics
Modules
  config      project paths, dataset config
  text        tokenization shared by retrieval and rules
  fndds       local FNDDS tables
  pipeline    Matcher: composes the components, writes run outputs + manifest
"""
