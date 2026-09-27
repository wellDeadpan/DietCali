source(here::here("R", "utils_io.R"))
source(here::here("R", "usda_client.R"))
source(here::here("R", "food_map_parsing.R"))
source(here::here("R", "derive_servings.R"))


paths <- load_paths()

ffq_path <- file.path(paths$ffq_raw_dir, "perls9.scn1.csv")
cache_path <- here::here("cache", "usda_fdc_search_cache.rds")

#cfg <- load_usda_config()

ffq <- read_data(ffq_path)

# FFQ food items -> USDA search terms (reviewed by hand, see
# scripts/make_ffq_search_terms_draft.py). Only item_type == "frequency" rows.
ffq_search <- read_ffq_search_terms()

ffq_search_parsed <- parse_var_map(ffq_search)

# failed queries are no longer cached, so the cache can be kept between runs.
# set to TRUE to force fresh USDA results (e.g. after changing the search logic)
refresh_cache <- FALSE
if (refresh_cache && file.exists(cache_path)) file.remove(cache_path)



cand_tbl <- usda_lookup_ffq_items(
  item_map_df = ffq_search_parsed,
  top_n = 10,
  data_types = c("FNDDS"),              
  cache_path = cache_path,
  sleep_sec = 0.2,
  verbose = TRUE
)



# drop candidates matching the `exclude` words, then keep one per var
rank1_best <- cand_tbl %>%
  apply_exclusions() %>%
  dedupe_keep_one_per_var()

rank1_best_weighted <- add_gramweight_from_usda(rank1_best)


# human proofreading for further improvement
