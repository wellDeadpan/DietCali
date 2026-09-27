#' USDA Client Functions
#'
#' Provides functions to interact with the USDA FoodData Central API.
#' @import httr jsonlite glue dplyr

`%||%` <- function(x, y) if (is.null(x)) y else x

load_usda_config <- function() {
  cfg <- yaml::read_yaml(here::here("config", "usda_config.yml"))
  
  # read API key from environment (e.g. FDC_API_KEY in ~/.Renviron)
  key_env <- cfg$api_key_env %||% "FDC_API_KEY"
  cfg$api_key <- Sys.getenv(key_env)
  if (!nzchar(cfg$api_key)) {
    stop("USDA API key not found. Set environment variable `", key_env,
         "` (e.g. add `", key_env, "=your_key` to ~/.Renviron and restart R).")
  }
  return(cfg)
}

usda_get_food <- function(fdc_id, format = "full", nutrients = NULL) {
  library(httr)
  library(jsonlite)
  cfg <- load_usda_config()
  url <- glue::glue("{cfg$base_url}/{cfg$version}/{cfg$endpoints$food}/{fdc_id}")
  params <- list(api_key = cfg$api_key, format = format)
  if (!is.null(nutrients)) params$nutrients <- paste(nutrients, collapse = ",")
  
  res <- httr::GET(url, query = params)
  stop_for_status(res)
  jsonlite::fromJSON(content(res, "text", encoding = "UTF-8"))
}

usda_search_foods <- function(query,
                              pageSize = NULL,
                              pageNumber = 1,
                              requireAllWords = FALSE,
                              dataType = NULL,
                              retries = 5) {
  library(httr)
  library(jsonlite)
  cfg <- load_usda_config()
  
  # endpoint
  url <- glue::glue("{cfg$base_url}/{cfg$version}/{cfg$endpoints$search}")
  
  # pass the raw query: httr URL-encodes query parameters itself,
  # so encoding here would double-encode (e.g. "apple juice" -> "apple%2520juice")
  
  params <- list(
    api_key = cfg$api_key,
    query = query,
    pageSize = if (is.null(pageSize)) cfg$default_pageSize else pageSize,
    pageNumber = pageNumber,
    requireAllWords = requireAllWords
  )
  
  # Optional: recommend to only select FNDD
  if (!is.null(dataType)) params$dataType <- dataType
  
  # automatic retry for error code 500/502/503/504
  res <- httr::RETRY(
    verb = "GET",
    url = url,
    query = params,
    times = retries,
    pause_base = 1,     # 1s, 2s, 4s...
    pause_cap = 16,
    terminate_on = c(200, 400, 401, 403, 404, 422) # retry won't help for these
  )
  
  # if keeps failing ,report to locate which query）
  if (httr::http_error(res)) {
    txt <- httr::content(res, as = "text", encoding = "UTF-8")
    stop("USDA FDC error (HTTP ", httr::status_code(res), ") for query=`", query, "`: ", txt)
  }
  
  jsonlite::fromJSON(httr::content(res, "text", encoding = "UTF-8"))
}

usda_get_multiple <- function(fdc_ids, format = "abridged") {
  cfg <- load_usda_config()
  url <- glue("{cfg$base_url}/{cfg$version}/{cfg$endpoints$foods}")
  params <- list(api_key = cfg$api_key, fdcIds = paste(fdc_ids, collapse = ","), format = format)
  
  res <- GET(url, query = params)
  stop_for_status(res)
  fromJSON(content(res, "text", encoding = "UTF-8"))
}

normalize_text <- function(x) {
  x <- tolower(x)
  x <- gsub("[^a-z0-9/ ]", " ", x)
  x <- gsub("\\s+", " ", x)
  trimws(x)
}

tokens <- function(x) {
  x <- normalize_text(x)
  t <- unlist(strsplit(x, " "))
  t[nzchar(t)]
}

prefix_score_one <- function(query, description, k = 4) {
  q <- unique(tokens(query))
  d <- tokens(description)
  
  if (length(q) == 0 || length(d) == 0) return(0)
  
  head_d <- unique(d[seq_len(min(k, length(d)))])
  full_d <- unique(d)
  
  head_cov <- mean(q %in% head_d)
  full_cov <- mean(q %in% full_d)
  
  mismatch_pen <- ifelse(head_cov < 0.34 && full_cov >= 0.34, 0.25, 0)
  
  q_first <- q[1]
  first_bonus <- ifelse(length(q_first) > 0 && q_first %in% head_d, 0.10, 0)
  
  0.65 * head_cov + 0.35 * full_cov + first_bonus - mismatch_pen
}


# map short data type names to the names the FDC API expects
.fdc_data_type_names <- c(
  FNDDS = "Survey (FNDDS)",
  Survey = "Survey (FNDDS)",
  Foundation = "Foundation",
  SR = "SR Legacy",
  Branded = "Branded"
)

usda_search_candidates <- function(item, top_n = 10, data_types = NULL, k_prefix = 4) {
  # restrict the search on the API side, so all returned results are of the
  # requested type(s) instead of filtering a mixed top-50 locally
  api_types <- NULL
  if (!is.null(data_types)) {
    api_types <- unique(ifelse(data_types %in% names(.fdc_data_type_names),
                               .fdc_data_type_names[data_types], data_types))
    api_types <- paste(api_types, collapse = ",")
  }
  res <- usda_search_foods(query = item, dataType = api_types)
  
  foods <- res$foods
  if (is.null(foods) || length(foods) == 0) {
    return(tibble::tibble(
      rank = integer(), fdcId = integer(), description = character(),
      dataType = character(), score = numeric(), foodCode = character(),
      error_msg = character(), prefix_score = numeric(), final = numeric()
    ))
  }
  
  foods_df <- as.data.frame(foods, stringsAsFactors = FALSE)
  if (nrow(foods_df) == 0) {
    return(tibble::tibble(
      rank = integer(), fdcId = integer(), description = character(),
      dataType = character(), score = numeric(), foodCode = character(),
      error_msg = character(), prefix_score = numeric(), final = numeric()
    ))
  }
  

  getcol <- function(df, nm, default) if (nm %in% names(df)) df[[nm]] else default
  n <- nrow(foods_df)
  
  df <- tibble::tibble(
    fdcId = as.integer(getcol(foods_df, "fdcId", rep(NA_integer_, n))),
    description = as.character(getcol(foods_df, "description", rep(NA_character_, n))),
    dataType = as.character(getcol(foods_df, "dataType", rep(NA_character_, n))),
    score = suppressWarnings(as.numeric(getcol(foods_df, "score", rep(NA_real_, n)))),
    foodCode = as.character(getcol(foods_df, "foodCode", rep(NA_character_, n))),
    error_msg = NA_character_
  )
  
  # safety net: also filter locally in case the API returns other types
  if (!is.null(data_types)) {
    if ("FNDDS" %in% data_types) {
      df <- df[grepl("FNDDS", df$dataType, ignore.case = TRUE) |
                 grepl("^Survey$", df$dataType, ignore.case = TRUE), , drop = FALSE]
    } else {
      df <- df[df$dataType %in% data_types, , drop = FALSE]
    }
  }
  
  if (nrow(df) == 0) {
    df$rank <- integer()
    df$prefix_score <- numeric()
    df$final <- numeric()
    return(df)
  }
  
  # prefix 分数 + 长度惩罚 + 融合原 API score
  df$prefix_score <- vapply(df$description, function(x) prefix_score_one(item, x, k = k_prefix), numeric(1))
  
  # 把 API 的 score 压到 0-1（避免它数量级压过 prefix_score）
  s <- df$score
  s01 <- if (all(is.na(s))) rep(0, length(s)) else {
    rng <- range(s, na.rm = TRUE)
    if (diff(rng) == 0) rep(0.5, length(s)) else (s - rng[1]) / (rng[2] - rng[1])
  }
  
  desc_len <- vapply(df$description, function(x) length(tokens(x)), integer(1))
  len_pen <- if (max(desc_len, na.rm = TRUE) == min(desc_len, na.rm = TRUE)) {
    rep(0, length(desc_len))
  } else {
    (desc_len - min(desc_len, na.rm = TRUE)) / (max(desc_len, na.rm = TRUE) - min(desc_len, na.rm = TRUE)) * 0.10
  }
  
  df$final <- 0.75 * df$prefix_score + 0.25 * s01 - len_pen
  
  # 按 final 排序并重设 rank
  df <- df[order(df$final, decreasing = TRUE), , drop = FALSE]
  df <- utils::head(df, top_n)
  df$rank <- seq_len(nrow(df))
  
  dplyr::as_tibble(df)
}




usda_lookup_ffq_items <- function(item_map_df,
                                  top_n = 10,
                                  data_types = NULL,
                                  cache_path = NULL,
                                  sleep_sec = 0.2,
                                  verbose = TRUE,
                                  ...) {
  stopifnot(all(c("var", "item") %in% names(item_map_df)))
  
  # ensure cache dir exists + load cache
  cache <- list()
  if (!is.null(cache_path)) {
    dirp <- dirname(cache_path)
    if (!dir.exists(dirp)) dir.create(dirp, recursive = TRUE, showWarnings = FALSE)
    if (file.exists(cache_path)) {
      cache <- readRDS(cache_path)
      if (!is.list(cache)) cache <- list()
    }
  }
  
  # cache key includes the search settings, so changing data_types / top_n
  # doesn't silently reuse results from a different search
  cache_key <- function(item) {
    paste0(item, " || ", paste(sort(data_types), collapse = ","), " || top", top_n)
  }
  
  uniq_items <- unique(item_map_df$item)
  to_query <- uniq_items[!cache_key(uniq_items) %in% names(cache)]
  
  # failed queries are kept here (not in the cache) so they are retried next run
  failed <- list()
  
  # helper: force schema (so unnest never breaks)
  force_schema <- function(x) {
    need <- c("rank","fdcId","description","dataType","score","foodCode","error_msg")
    for (nm in setdiff(need, names(x))) x[[nm]] <- NA
    x <- x[, need, drop = FALSE]
    tibble::as_tibble(x)
  }
  
  if (length(to_query) > 0) {
    if (verbose) message("🔎 Querying USDA FDC for ", length(to_query), " new items ...")
    
    # save successful results even if the loop is interrupted
    if (!is.null(cache_path)) on.exit(saveRDS(cache, cache_path), add = TRUE)
    
    for (q in to_query) {
      Sys.sleep(sleep_sec)
      
      cand <- tryCatch(
        {
          tmp <- usda_search_candidates(
            item = q,
            top_n = top_n,
            data_types = data_types
          )
          
          if (!("error_msg" %in% names(tmp))) tmp$error_msg <- NA_character_
          tmp <- force_schema(tmp)
          
          if (verbose) message("OK: ", q, " | nrow=", nrow(tmp))
          tmp
        },
        error = function(e) {
          msg <- conditionMessage(e)
          if (verbose) message("❌ ERROR: ", q, " | ", msg)
          
          # one row carrying the error message, so the failure shows up in the output
          tmp <- tibble::tibble(error_msg = msg)
          force_schema(tmp)
        }
      )
      
      if (all(is.na(cand$error_msg))) {
        cache[[cache_key(q)]] <- cand
      } else {
        failed[[q]] <- cand
      }
    }
    
    if (length(failed) > 0) {
      warning(length(failed), " item(s) failed and were not cached (will be retried next run): ",
              paste(names(failed), collapse = "; "), call. = FALSE)
    }
  } else {
    if (verbose) message("✅ All items found in cache; no API calls needed.")
  }
  
  # ---- keep columns from item_map_df, including food_group / portion_amount / portion_unit ----
  keep_cols <- intersect(
    c("var","item","food_group","portion_amount","portion_unit"),
    names(item_map_df)
  )
  
  out <- item_map_df %>%
    dplyr::select(dplyr::all_of(keep_cols), dplyr::everything()) %>%  # 只是把关键列放前面
    dplyr::mutate(
      candidates = purrr::map(.data$item, ~ failed[[.x]] %||% cache[[cache_key(.x)]] %||% tibble::tibble())
    ) %>%
    tidyr::unnest(candidates, keep_empty = TRUE)
  
  dplyr::as_tibble(out)
}






#' Search foods (user-friendly summary)
#'
#' @param query character, keyword(s) like "donut" or "apple"
#' @param limit integer, max results
#' @return tibble with description, dataType, measures and fdcId
#'
search_foods_simple <- function(query, limit = 10, sleep_sec = 0.4) {
  if (is.na(query) || query == "") return(NULL)
  
  # Try–catch in case of HTTP 500 or config error
  res <- try(usda_search_foods(query = query, pageSize = limit), silent = TRUE)
  if (inherits(res, "try-error") || is.null(res)) {
    message(sprintf("⚠️ Skipped '%s' (request failed)", query))
    return(tibble(food_item = query,
                  fdcId = NA, description = NA,
                  dataType = NA, brandOwner = NA))
  }
  
  # Defensive: the API might return an error JSON rather than a foods list
  if (!"foods" %in% names(res) || is.null(res$foods)) {
    message(sprintf("⚠️ No results for '%s'", query))
    return(tibble(food_item = query,
                  fdcId = NA, description = NA,
                  dataType = NA, brandOwner = NA))
  }


  # Pause slightly between requests
  #Sys.sleep(sleep_sec)
  
  tibble(
    food_item   = query,
    fdcId       = res$foods$fdcId,
    description = res$foods$description,
    dataType    = res$foods$dataType,
    brandOwner  = res$foods$brandOwner
  )
}

#' Get food details with measure and nutrient summary
#'
#' @param fdc_id numeric or character (single)
#' @return list with description, measures, nutrients
#'
get_food_details <- function(fdc_id) {
  library(dplyr)
  dat <- usda_get_food(fdc_id)
  # ---- extract general info ----
  info <- tibble::tibble(
    fdcId = dat$fdcId,
    description = dat$description,
    dataType = dat$dataType
    # food group?
  )
  
  # ---- extract measures ----
  measures <- dat$foodPortions %>%
    dplyr::select(disseminationText = portionDescription,
                  gramWeight)
  
  # ---- extract selected nutrients ----
  flat <- jsonlite::flatten(dat$foodNutrients)
  nutrients <- flat %>%
    dplyr::select(
      nutrient = nutrient.name,
      value = amount,
      unit = nutrient.unitName
    )
  
  
  list(
    info = info,
    measures = measures,
    nutrients = nutrients
  )
  
}

check_usda_updates <- function(days_back = 30) {
  cfg <- load_usda_config()
  api_key <- cfg$api_key
  base_url <- cfg$base_url
  version <- cfg$version
  
  url <- glue::glue("{base_url}/{version}/{cfg$endpoints$search}")
  params <- list(
    api_key = api_key,
    sortBy = "publicationDate",
    sortOrder = "desc",
    pageSize = 5
  )
  
  res <- httr::GET(url, query = params)
  httr::stop_for_status(res)
  data <- jsonlite::fromJSON(httr::content(res, "text", encoding = "UTF-8"))
  
  tib <- tibble::as_tibble(data$foods) %>%
    dplyr::select(fdcId, description, dataType, publicationDate)
  
  latest_date <- max(as.Date(tib$publicationDate))
  
  message("✅ Latest USDA update: ", latest_date)
  tib
}


