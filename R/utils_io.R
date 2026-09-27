# Paths are resolved relative to the project root (folder containing `.here`)
# via here::here(), so scripts work regardless of the working directory.

# Load external data locations from config/paths.yml.
# Relative entries are resolved against the project root; absolute ones kept as-is.
load_paths <- function(path_yaml = here::here("config", "paths.yml")) {
  p <- yaml::read_yaml(path_yaml)
  lapply(p, function(x) {
    if (grepl("^(/|~|[A-Za-z]:)", x)) path.expand(x) else here::here(x)
  })
}

read_usda_config <- function(path_yaml = here::here("config", "nutrient_reference.yml")) {
  yaml::read_yaml(path_yaml)
}

#' Read input data (supports CSV, XLS, XLSX)
#'
#' Automatically detects file extension and reads accordingly.
#' Returns a data.frame / tibble.
#' Requires: readr, readxl, dplyr
#'
#' @param path Path to the input file.
#' @param sheet Optional sheet name or index for Excel files.
#' @param ... Additional arguments passed to read_csv() or read_excel().
#'
#' @return tibble
#' @examples
#' ffq <- read_data("data_raw/FFQ_raw.csv")
#' nut <- read_data("data_raw/nutrient_raw.xlsx", sheet = 1)

read_data <- function(path, sheet = 1, ...) {
  library(dplyr)
  ext <- tolower(tools::file_ext(path))
  
  if (!file.exists(path)) {
    stop(glue::glue("❌ File not found: {path}"))
  }
  
  message(glue::glue("📂 Reading file: {basename(path)} (.{ext})"))
  
  switch(
    ext,
    csv = readr::read_csv(path, show_col_types = FALSE, ...),
    xlsx = readxl::read_excel(path, sheet = sheet, ...),
    xls = readxl::read_excel(path, sheet = sheet, ...),
    stop(glue::glue("Unsupported file type: .{ext}. Please provide csv, xlsx, or xls."))
  ) %>% dplyr::as_tibble()
}

read_ffq_item_map <- function(path) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  
  # remove empty rows and comment rows
  lines <- trimws(lines)
  lines <- lines[nzchar(lines)]
  lines <- lines[!grepl("^#", lines)]
  
  # keep only rows with "=" sign
  lines <- lines[grepl("=", lines, fixed = TRUE)]
  
  # split into variables and food question items
  split_once <- function(x) {
    parts <- strsplit(x, "=", fixed = TRUE)[[1]]
    var <- trimws(parts[1])
    item <- trimws(paste(parts[-1], collapse = "="))  # in case food question item includes "="
    c(var = var, item = item)
  }
  
  mat <- t(vapply(lines, split_once, FUN.VALUE = c(var = "", item = "")))
  tibble::tibble(var = mat[, "var"], item = mat[, "item"])
}

#' Read the reviewed FFQ search-term table (config/ffq_search_terms.csv)
#'
#' Returns one row per (var, search term), ready for usda_lookup_ffq_items():
#'   var, descriptions (original FFQ label), item (= search term, what USDA is
#'   queried with), entity (= search term, its last word is the head word),
#'   exclude, food_group, portion, item_type
#'
#' @param item_types which item_type rows to keep (default: food-frequency items only)
read_ffq_search_terms <- function(path = here::here("config", "ffq_search_terms.csv"),
                                  item_types = "frequency") {
  tbl <- readr::read_csv(path, show_col_types = FALSE,
                         col_types = readr::cols(.default = readr::col_character()))
  
  missing_terms <- tbl$var[tbl$item_type %in% item_types & (is.na(tbl$search_terms) | trimws(tbl$search_terms) == "")]
  if (length(missing_terms) > 0) {
    stop("search_terms is empty for: ", paste(missing_terms, collapse = ", "))
  }
  
  tbl %>%
    dplyr::filter(.data$item_type %in% item_types) %>%
    dplyr::rename(descriptions = "item") %>%
    dplyr::mutate(search_term = strsplit(.data$search_terms, ";", fixed = TRUE)) %>%
    tidyr::unnest_longer("search_term") %>%
    dplyr::mutate(search_term = trimws(.data$search_term)) %>%
    dplyr::filter(.data$search_term != "") %>%
    dplyr::mutate(item = .data$search_term, entity = .data$search_term) %>%
    dplyr::select("var", "descriptions", "item", "entity", "exclude",
                  "food_group", "portion", "item_type")
}
