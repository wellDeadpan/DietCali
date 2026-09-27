# This script checks for USDA updates and downloads new data.

source(here::here("R", "usda_client.R"))
source(here::here("R", "usda_cache.R"))

update_usda_data <- function(query = "donut", limit = 10) {
  message("🔍 Searching for: ", query)
  res <- usda_search_foods(query = query, pageSize = limit)
  
  foods <- res$foods
  message("✅ Found ", nrow(foods), " items.")
  
  purrr::walk(foods$fdcId, ~{
    message("⬇️ Caching food: ", .x)
    cache_usda_food(.x)
  })
  
  invisible(foods)
}

# Example run
update_usda_data("donut", limit = 5)
