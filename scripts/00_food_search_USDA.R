source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/utils_io.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/usda_client.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/food_map_parsing.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/derive_servings.R")


ffq_path <- "/restricted/projectnb/iloredcap/data/ILO_FFQ_data/FFQ Data Harvard 28JULY2025/perls9/perls9.scn1.csv"
ffq_item_path <- "/restricted/projectnb/iloredcap/data/ILO_FFQ_data/FFQ Data Harvard 28JULY2025/perls9/perls9.scn1.csv.label.doc"
cache_path <- "/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/cache/usda_fdc_search_cache.rds"
ffq_python_path <- "/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/cache/ffq_item_map_parsed.rds"

#cfg <- load_usda_config()

ffq <- read_data(ffq_path)
ffq_item <- read_ffq_item_map(ffq_item_path)
ffq_item_py <- readRDS(ffq_python_path)
ffq_item_py <- ffq_item_py %>% rename(descriptions = item, item = entity_modifiers)

ffq_item_py <- ffq_item_py[88:367,]

# use：
ffq_item_py_parsed <- parse_var_map(ffq_item_py)

file.remove(cache_path)  



cand_tbl <- usda_lookup_ffq_items(
  item_map_df = ffq_item_py_parsed,
  top_n = 10,
  data_types = c("FNDDS"),              
  cache_path = cache_path,
  sleep_sec = 0.2,
  verbose = TRUE
)



rank1_best <- dedupe_keep_one_per_var(cand_tbl)

rank1_best_weighted <- add_gramweight_from_usda(rank1_best)


# human proofreading for further improvement
