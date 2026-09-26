correct_ids <- function(df, id_map) {
  df %>% dplyr::left_join(id_map, by = "old_id") %>% 
    dplyr::mutate(id = dplyr::coalesce(new_id, old_id))
}

# Validate and parse FFQ frequency conversion YAML
# Returns a named numeric vector: code -> servings/day

util_check_freq_conversion <- function(yml_path,
                                       allow_values = 1:9,
                                       key = "freq_conversion") {
  
  # ---- read YAML ----
  y <- yaml::read_yaml(yml_path)
  
  if (!(key %in% names(y))) {
    stop("YAML must contain a top-level key `", key, "`.")
  }
  
  map_tbl <- tibble::as_tibble(y[[key]])
  
  # ---- schema validation ----
  required_cols <- c("value", "coefficient")
  missing <- setdiff(required_cols, names(map_tbl))
  if (length(missing) > 0) {
    stop(
      "freq_conversion missing required column(s): ",
      paste(missing, collapse = ", ")
    )
  }
  
  # ---- semantic cleaning ----
  map_tbl <- map_tbl %>%
    dplyr::mutate(
      value = as.character(.data$value),
      coefficient = dplyr::na_if(as.character(.data$coefficient), "."),
      coefficient = as.numeric(.data$coefficient)
    )
  
  # ---- logical validation ----
  if (anyDuplicated(map_tbl$value)) {
    stop("Duplicate response codes detected in freq_conversion.")
  }
  
  allowed_chr <- as.character(allow_values)
  
  extra_codes <- setdiff(map_tbl$value, allowed_chr)
  missing_codes <- setdiff(allowed_chr, map_tbl$value)
  
  if (length(extra_codes) > 0) {
    stop(
      "Unexpected response code(s) in freq_conversion: ",
      paste(extra_codes, collapse = ", ")
    )
  }
  
  if (length(missing_codes) > 0) {
    stop(
      "Missing response code(s) in freq_conversion: ",
      paste(missing_codes, collapse = ", ")
    )
  }
  
  if (any(map_tbl$coefficient < 0, na.rm = TRUE)) {
    stop("Negative coefficients detected in freq_conversion.")
  }
  
  # ---- return mapping vector ----
  stats::setNames(map_tbl$coefficient, map_tbl$value)
}
