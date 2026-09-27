source(here::here("R", "utils_io.R"))
source(here::here("R", "usda_client.R"))
source(here::here("R", "food_map_parsing.R"))
source(here::here("R", "derive_servings.R"))


paths <- load_paths()

ffq_path <- file.path(paths$ffq_raw_dir, "perls9.scn1.csv")
ffq_item_path <- file.path(paths$ffq_raw_dir, "perls9.scn1.csv.label.doc")
cache_path <- here::here("cache", "usda_fdc_search_cache.rds")
ffq_python_path <- here::here("cache", "ffq_item_map_parsed.rds")

#cfg <- load_usda_config()

ffq <- read_data(ffq_path)
ffq_item <- read_ffq_item_map(ffq_item_path)
ffq_item_py <- readRDS(ffq_python_path)
ffq_item_py <- ffq_item_py %>% rename(descriptions = item, item = entity_modifiers)

ffq_item_py <- ffq_item_py[88:367,]

# use：
ffq_item_py_parsed <- parse_var_map(ffq_item_py)

# failed queries are no longer cached, so the cache can be kept between runs.
# set to TRUE to force fresh USDA results (e.g. after changing the search logic)
refresh_cache <- FALSE
if (refresh_cache && file.exists(cache_path)) file.remove(cache_path)



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
