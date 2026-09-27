#' Caching functions to store USDA API responses

usda_cache_dir <- function() {
  dir <- here::here("data_raw", "usda", "cache")
  if (!dir.exists(dir)) dir.create(dir, recursive = TRUE)
  dir
}

usda_cache_path <- function(fdc_id) {
  file.path(usda_cache_dir(), paste0(fdc_id, ".json"))
}

cache_usda_food <- function(fdc_id, force_refresh = FALSE) {
  path <- usda_cache_path(fdc_id)
  if (file.exists(path) && !force_refresh) {
    return(fromJSON(path))
  }
  dat <- usda_get_food(fdc_id)
  write_json(dat, path, pretty = TRUE, auto_unbox = TRUE)
  dat
}
