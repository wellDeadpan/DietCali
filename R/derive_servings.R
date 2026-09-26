#' Convert FFQ coded responses to servings per day
#'
#' @param ffq_df data.frame containing coded responses (columns = FFQ questions)
#' @param config_path path to CSV/XLSX mapping table
#' @param id_var optional respondent ID column name
#'
#' @return tibble with same columns converted to servings/day
#' @examples
#' ffq_servings <- convert_to_servings(ffq_raw, "config/freq_to_servings.csv")

# derive_servings.R
# Convert FFQ coded responses to daily servings

convert_to_daily_servings <- function(ffq_df,
                            yml_path,
                            id_var = NULL,
                            ffq_cols = NULL) {
  
  # ---- get validated mapping ----
  map_vec <- util_check_freq_conversion(yml_path)
  
  # ---- decide FFQ columns ----
  if (is.null(ffq_cols)) {
    ffq_cols <- setdiff(names(ffq_df), id_var)
  } else {
    ffq_cols <- intersect(ffq_cols, names(ffq_df))
    if (length(ffq_cols) == 0) {
      stop("No ffq_cols found in ffq_df.")
    }
  }
  
  # ---- convert ----
  converted <- purrr::map_dfc(ffq_cols, function(col) {
    x_chr <- as.character(ffq_df[[col]])
    
    out <- dplyr::recode(
      x_chr,
      !!!map_vec,
      .default = NA_real_
    )
    
    tibble::tibble(!!col := as.numeric(out))
  })
  
  # ---- bind ID back ----
  if (!is.null(id_var) && id_var %in% names(ffq_df)) {
    converted <- dplyr::bind_cols(ffq_df[id_var], converted)
  }
  
  dplyr::as_tibble(converted)
}

unit_to_patterns <- function(u) {
  if (is.null(u) || length(u) == 0 || is.na(u)) return(character(0))
  
  u <- tolower(str_trim(u))
  if (u == "") return(character(0))
  
  if (u %in% c("ounce", "oz"))        return(c("fl oz", "\\boz\\b"))
  if (u %in% c("cup", "cp"))          return(c("\\bcup\\b"))
  if (u %in% c("tablespoon","tbsp"))  return(c("\\btbsp\\b","tablespoon"))
  if (u %in% c("teaspoon","tsp"))     return(c("\\btsp\\b","teaspoon"))
  if (u %in% c("gram","g"))           return(c("\\bg\\b","gram"))
  if (u %in% c("milliliter","ml"))    return(c("\\bml\\b","milliliter"))
  
  return(c(str_replace_all(u, "\\s+", "\\\\s+")))
}

extract_amount_from_portion_desc <- function(desc) {
  if (is.na(desc) || desc == "") return(1)
  
  q <- str_extract(desc, "(\\d+\\s*/\\s*\\d+|\\d+\\s*[-–]\\s*\\d+|\\d+(?:\\.\\d+)?)")
  if (is.na(q)) return(1)
  
  parse_quantity(q)
}

pick_portion_row <- function(foodPortions_df, portion_unit) {
  
  if (is.null(foodPortions_df) || nrow(foodPortions_df) == 0) {
    return(tibble(
      portionDescription_match = NA_character_,
      gramWeight_raw = NA_real_,
      portion_desc_amount = NA_real_,
      grams_per_unit = NA_real_,
      portion_match_warning = "foodPortions empty"
    ))
  }
  
  fp <- as_tibble(foodPortions_df) %>%
    mutate(portionDescription_lc = tolower(portionDescription %||% ""))
  
  pats <- unit_to_patterns(portion_unit)
  if (length(pats) == 0) {
    return(tibble(
      portionDescription_match = NA_character_,
      gramWeight_raw = NA_real_,
      portion_desc_amount = NA_real_,
      grams_per_unit = NA_real_,
      portion_match_warning = "portion_unit missing"
    ))
  }
  
  hit_idx <- NA_integer_
  for (p in pats) {
    idx <- which(str_detect(fp$portionDescription_lc, regex(p, ignore_case = TRUE)))
    if (length(idx) > 0) { hit_idx <- idx[1]; break }
  }
  
  if (is.na(hit_idx)) {
    return(tibble(
      portionDescription_match = NA_character_,
      gramWeight_raw = NA_real_,
      portion_desc_amount = NA_real_,
      grams_per_unit = NA_real_,
      portion_match_warning = paste0("no match for unit: ", portion_unit)
    ))
  }
  
  desc <- fp$portionDescription[hit_idx]
  gw   <- as.numeric(fp$gramWeight[hit_idx])
  
  desc_amt <- extract_amount_from_portion_desc(desc)
  grams_per_unit <- gw / desc_amt
  
  tibble(
    portionDescription_match = desc,
    gramWeight_raw = gw,
    portion_desc_amount = desc_amt,
    grams_per_unit = grams_per_unit,
    portion_match_warning = NA_character_
  )
}


add_gramweight_from_usda <- function(rank1_best,
                                     fdc_col = "fdcId",
                                     unit_col = "portion_unit",
                                     qty_col  = "portion_amount",
                                     sleep_sec = 0.2) {
  
  stopifnot(all(c(fdc_col, unit_col, qty_col) %in% names(rank1_best)))
  
  rank1_best %>%
    mutate(
      .food = map(.data[[fdc_col]], function(id) {
        Sys.sleep(sleep_sec)
        tryCatch(usda_get_food(id), error = function(e) e)
      }),
      .portion_match = pmap(
        list(.food, .data[[unit_col]]),
        function(food_obj, u) {
          
          if (inherits(food_obj, "error") || inherits(food_obj, "simpleError")) {
            return(tibble(
              portionDescription_match = NA_character_,
              gramWeight_raw = NA_real_,
              portion_desc_amount = NA_real_,
              grams_per_unit = NA_real_,
              portion_match_warning = paste0("usda_get_food error: ", conditionMessage(food_obj))
            ))
          }
          
          fp <- NULL
          if (is.list(food_obj) && "foodPortions" %in% names(food_obj)) fp <- food_obj[["foodPortions"]]
          if (is.data.frame(food_obj) && "foodPortions" %in% names(food_obj)) fp <- food_obj[["foodPortions"]]
          
          pick_portion_row(fp, u)
        }
      )
    ) %>%
    unnest_wider(.portion_match) %>%
    mutate(
      grams_total = grams_per_unit * .data[[qty_col]]
    ) %>%
    select(-.food)
}