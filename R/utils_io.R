read_usda_config <- function(path_yaml = "/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/config/nutrient_reference.yml") {
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