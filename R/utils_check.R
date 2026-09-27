correct_ids <- function(df, id_map) {
  df %>% dplyr::left_join(id_map, by = "old_id") %>% 
    dplyr::mutate(id = dplyr::coalesce(new_id, old_id))
}

# Validate and parse FFQ frequency conversion YAML
# Returns a named numeric vector: code -> servings/day
#
# Response codes are taken from the YAML itself, so different inputs
# (FFQ food items now, other instruments later) can use their own codes.
# Pass `allow_values` only to additionally enforce an exact expected code set.

util_check_freq_conversion <- function(yml_path,
                                       allow_values = NULL,
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
  
  if (nrow(map_tbl) == 0) {
    stop("freq_conversion is empty.")
  }
  
  # ---- semantic cleaning ----
  # "." means no fixed coefficient (e.g. "Pass through") -> NA
  coef_chr <- dplyr::na_if(trimws(as.character(map_tbl$coefficient)), ".")
  coef_num <- suppressWarnings(as.numeric(coef_chr))
  bad_coef <- !is.na(coef_chr) & is.na(coef_num)
  if (any(bad_coef)) {
    stop(
      "Non-numeric coefficient(s) in freq_conversion for code(s): ",
      paste(map_tbl$value[bad_coef], collapse = ", ")
    )
  }
  
  map_tbl <- map_tbl %>%
    dplyr::mutate(
      value = as.character(.data$value),
      coefficient = coef_num
    )
  
  # ---- logical validation ----
  if (anyDuplicated(map_tbl$value)) {
    stop("Duplicate response codes detected in freq_conversion.")
  }
  
  if (!is.null(allow_values)) {
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
  }
  
  if (any(map_tbl$coefficient < 0, na.rm = TRUE)) {
    stop("Negative coefficients detected in freq_conversion.")
  }
  
  # ---- return mapping vector ----
  stats::setNames(map_tbl$coefficient, map_tbl$value)
}
