library(dplyr)
library(stringr)
library(purrr)
library(tidyr)
library(readxl)
library(writexl)


# ---- helpers (keep yours) ----
parse_quantity <- function(x) {
  if (is.na(x) || x == "") return(1)
  x <- str_trim(x)
  x <- str_remove_all(x, '"|”|′|″')
  x <- str_replace_all(x, "\\s", "")
  if (str_detect(x, "^\\d+/\\d+$")) {
    parts <- as.numeric(str_split(x, "/", simplify = TRUE))
    return(parts[1] / parts[2])
  }
  if (str_detect(x, "^\\d+[-–]\\d+$")) {
    parts <- as.numeric(str_split(x, "[-–]", simplify = TRUE))
    return(mean(parts))
  }
  suppressWarnings(as.numeric(x))
}

norm_unit <- function(u) {
  if (is.na(u) || u == "") return(NA_character_)
  u <- str_to_lower(str_squish(u))
  u <- word(u, 1)
  u <- str_replace(u, "^cp$", "cup")
  u <- str_replace(u, "^oz$", "ounce")
  u <- str_replace(u, "^(tb|tbsp)$", "tablespoon")
  u <- str_replace(u, "^(ts|tsp)$", "teaspoon")
  u <- str_replace(u, "^pat$", "pat")
  u <- str_replace(u, "^clove$", "clove")
  u <- str_replace(u, "^stick$", "stick")
  u <- str_replace(u, "^ear$", "ear")
  u <- str_replace(u, "^(bag|pack)$", "pack")
  u <- str_replace(u, "^glass$", "glass")
  u <- str_replace(u, "^cpn?$", "cup")
  u
}

# ---- NEW: parse a single portion string into amount + unit, with preference rules ----
parse_portion_preferred <- function(portion_str,
                                    standard_units = c("ounce","gram","milliliter","ml","cup","tablespoon","teaspoon"),
                                    prefer_order   = c("ounce","gram","milliliter","ml","cup","tablespoon","teaspoon")) {
  if (is.na(portion_str) || str_trim(portion_str) == "") {
    return(tibble(portion_amount = NA_real_, portion_unit = NA_character_, portion_chosen = NA_character_))
  }
  
  x <- str_to_lower(str_squish(portion_str))
  # split by "or"
  variants <- str_split(x, "\\s+or\\s+", simplify = FALSE)[[1]] %>%
    str_squish() %>% discard(~ .x == "")
  
  if (length(variants) == 0) {
    return(tibble(portion_amount = NA_real_, portion_unit = NA_character_, portion_chosen = NA_character_))
  }
  
  # extract amount + unit per variant
  var_tbl <- tibble(variant = variants) %>%
    mutate(
      # number: fraction | range | integer/decimal
      qty_raw = str_extract(variant, "(\\d+\\s*/\\s*\\d+|\\d+\\s*[-–]\\s*\\d+|\\d+(?:\\.\\d+)?)"),
      portion_amount = map_dbl(qty_raw, parse_quantity),
      unit_raw = str_remove(variant, "(\\d+\\s*/\\s*\\d+|\\d+\\s*[-–]\\s*\\d+|\\d+(?:\\.\\d+)?)") %>%
        str_squish() %>%
        str_remove_all("^[[:punct:]\\s]+|[[:punct:]\\s]+$"),
      portion_unit = map_chr(unit_raw, norm_unit),
      is_standard = !is.na(portion_unit) & portion_unit %in% standard_units,
      pref_rank = ifelse(is_standard, match(portion_unit, prefer_order), Inf)
    )
  
  # selection rule:
  # 1) if any standard unit exists -> pick the smallest pref_rank (ties -> first)
  # 2) else -> pick the first variant
  pick_idx <- if (any(var_tbl$is_standard, na.rm = TRUE)) {
    which.min(var_tbl$pref_rank)
  } else {
    1
  }
  
  chosen <- var_tbl[pick_idx, , drop = FALSE]
  
  tibble(
    portion_amount = chosen$portion_amount,
    portion_unit   = chosen$portion_unit,
    portion_chosen = chosen$variant
  )
}

# ---- UPDATED main parser ----
# 适配两种来源：
# - 老格式：variable_label -> portion_text
# - 新格式：直接有 portion 列
parse_var_map <- function(var_map) {
  
  parsed <- var_map %>%
    mutate(
      # 如果是老格式（variable_label存在）就沿用；新格式可缺失
      food_group = if ("variable_label" %in% names(var_map)) str_trim(str_extract(variable_label, "^[^-]+")) else NA_character_,
      after_dash = if ("variable_label" %in% names(var_map)) str_trim(str_remove(variable_label, "^[^-]+-")) else NA_character_,
      
      # 老逻辑：从 variable_label 里抓括号做 portion_text
      all_paren = if ("variable_label" %in% names(var_map)) str_extract_all(after_dash, "\\([^)]*\\)") else list(character(0)),
      portion_text_old = map_chr(all_paren, ~ ifelse(length(.x) > 0, str_remove_all(tail(.x, 1), "\\(|\\)"), NA_character_)),
      
      # 新格式：如果已有 portion 列，就用它覆盖
      portion_text = if ("portion" %in% names(var_map)) coalesce(portion, portion_text_old) else portion_text_old
    ) %>%
    # 关键：把 portion_text 清洗成 amount/unit（并做单位优先级选择）
    mutate(portion_parsed = map(portion_text, parse_portion_preferred)) %>%
    unnest_wider(portion_parsed)
  
  parsed
}




# Save result for USDA search / caching step
#writexl::write_xlsx(var_map_parsed, here::here("config", "variable_mapping_parsed.xlsx"))

message("✅ Parsed mapping saved to config/variable_mapping_parsed.xlsx")


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

suppressPackageStartupMessages({
  library(dplyr)
  library(stringr)
  library(purrr)
})

.normalize_text <- function(x) {
  x %>%
    as.character() %>%
    str_to_lower() %>%
    str_replace_all("[\\-_/]", " ") %>%
    str_replace_all("[[:punct:]]+", " ") %>%
    str_squish()
}

.default_stopwords <- c(
  "fresh","raw","cooked","frozen","dry","dried","reduced","fat","low","nonfat",
  "skim","whole","percent","stage","baby","toddler","human","nfs","ns",
  "and","or","with","without","in","of","to"
)

.simple_lemma <- function(tok) {
  tok <- str_squish(tok)
  ifelse(nchar(tok) >= 4, str_replace(tok, "s$", ""), tok)
}

.tokenize <- function(x, stopwords = .default_stopwords) {
  x <- .normalize_text(x)
  if (is.na(x) || x == "") return(character(0))
  toks <- str_split(x, "\\s+")[[1]]
  toks <- toks[toks != ""]
  toks <- toks[!toks %in% stopwords]
  toks <- .simple_lemma(toks)
  toks[toks != ""]
}

.get_head <- function(entity, stopwords = .default_stopwords) {
  toks <- .tokenize(entity, stopwords)
  if (length(toks) == 0) return(NA_character_)
  toks[length(toks)]
}

.jaccard <- function(a, b) {
  a <- unique(a); b <- unique(b)
  if (length(a) == 0 && length(b) == 0) return(1)
  if (length(a) == 0 || length(b) == 0) return(0)
  length(intersect(a, b)) / length(union(a, b))
}

# =========================================================
# 主函数：每个 var 只保留 1 条
# - 先 filter(rank==1)
# - 核心词(head)必须出现在候选description里
# - similarity最高者胜出；并列用score打破
# =========================================================
dedupe_keep_one_per_var <- function(df,
                                    var_col = "var",
                                    rank_col = "rank",
                                    entity_col = "entity",
                                    query_desc_col = "descriptions",
                                    cand_desc_col = "description",
                                    score_col = "score",
                                    stopwords = .default_stopwords,
                                    w_querydesc = 1.0) {
  
  stopifnot(all(c(var_col, rank_col, entity_col, query_desc_col, cand_desc_col) %in% names(df)))
  
  x <- df %>%
    filter(.data[[rank_col]] == 1) %>%
    mutate(
      .head = map_chr(.data[[entity_col]], ~ .get_head(.x, stopwords)),
      .q_tokens = map(.data[[query_desc_col]], ~ .tokenize(.x, stopwords)),
      .cand_tokens = map(.data[[cand_desc_col]], ~ .tokenize(.x, stopwords)),
      # 核心词一致：候选必须含 head
      .head_ok = map2_lgl(.head, .cand_tokens, ~ !is.na(.x) && .x %in% .y),
      # similarity（这里用 query descriptions vs candidate 的 Jaccard；你也可以换更复杂）
      .sim = map2_dbl(.q_tokens, .cand_tokens, .jaccard) * w_querydesc,
      # 不满足核心词一致的直接淘汰
      .sim = ifelse(.head_ok, .sim, -Inf)
    )
  
  # 如果一个 var 下所有候选都 head_ok=FALSE，.sim 全是 -Inf
  # 这种情况下：退一步用 score 最高的（避免整个 var 被丢掉）
  has_score <- score_col %in% names(x)
  
  x %>%
    group_by(.data[[var_col]]) %>%
    mutate(.all_bad = all(is.infinite(.sim) & .sim < 0)) %>%
    {
      if (has_score) {
        arrange(., desc(ifelse(.all_bad, .data[[score_col]], .sim)),
                desc(.data[[score_col]]), .by_group = TRUE)
      } else {
        arrange(., desc(ifelse(.all_bad, 0, .sim)), .by_group = TRUE)
      }
    } %>%
    slice(1) %>%
    ungroup() %>%
    select(-.head, -.q_tokens, -.cand_tokens, -.head_ok, -.sim, -.all_bad)
}
