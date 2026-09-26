# convert into daily servings
load_ffq_config <- function() {
  cfg <- yaml::read_yaml("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/config/ffq_conversion.yml")
  return(cfg)
}


library(dplyr)
library(purrr)


ffq_daily <- ffq %>%
  mutate(across(-ID, ~ freq_conversion$coefficient[match(., freq_conversion$value)]))


portion_table <- tibble::tribble(
  ~food, ~grams_per_serving,
  "milk", 240,
  "yogurt", 150,
  "tofu", 100
)

# 转成长格式，计算 daily grams
ffq_long <- ffq_daily %>%
  pivot_longer(-ID, names_to = "food", values_to = "daily_serving") %>%
  left_join(portion_table, by = "food") %>%
  mutate(grams_per_day = daily_serving * grams_per_serving)


ffq_wide_grams <- ffq_long %>%
  select(ID, food, grams_per_day) %>%
  pivot_wider(names_from = food, values_from = grams_per_day)


convert_ffq_to_daily <- function(ffq, freq_table, portion_table = NULL) {
  ffq_daily <- ffq %>%
    mutate(across(-ID, ~ freq_table$coefficient[match(., freq_table$value)]))
  
  if (!is.null(portion_table)) {
    ffq_daily_long <- ffq_daily %>%
      pivot_longer(-ID, names_to = "food", values_to = "daily_serving") %>%
      left_join(portion_table, by = "food") %>%
      mutate(grams_per_day = daily_serving * grams_per_serving)
    
    return(ffq_daily_long)
  }
  
  return(ffq_daily)
}