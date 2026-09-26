derive_foodgroups <- function(df) {
  df %>%
    dplyr::mutate(
      total_fruit = rowSums(dplyr::select(., rais05h, prun05h, ban05h, apple05h, orangejuice05h), na.rm = TRUE),
      whole_fruit = rowSums(dplyr::select(., rais05h, ban05h, apple05h), na.rm = TRUE)
    )
}
