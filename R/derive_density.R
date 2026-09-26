derive_density <- function(df, energy_var, nutrient_vars) {
  df %>%
    dplyr::mutate(dplyr::across(all_of(nutrient_vars),
      ~ .x / (!!sym(energy_var) / 1000),
      .names = "{.col}_density"
    ))
}
