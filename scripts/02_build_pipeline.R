source(here::here("R", "utils_io.R"))
source(here::here("R", "utils_check.R"))
source(here::here("R", "derive_density.R"))
source(here::here("R", "derive_servings.R"))
source(here::here("R", "derive_foodgroups.R"))

datpth <- load_paths()$necs_data_dir

cfg  <- read_usda_config()

ffq <- read_data(file.path(datpth, "DQ scores for foods 10 November 2005 with import headers.xls"), skip=1)
nutrients <- read_data(file.path(datpth, "DQ file 9 Nov 2005.csv"))

hei_ready <- data$ffq %>%
  correct_ids(readr::read_csv(here::here("data_raw", "id_crosswalk.csv"))) %>%
  convert_to_servings(freq_vars = grep("05d$", names(.), value = TRUE),
                      conv_table = readr::read_csv(here::here("config", "freq_to_servings.csv"))) %>%
  derive_foodgroups() %>%
  derive_density("calories", c("HEItotfru05", "HEIveg05")) %>%
  calc_HEI2015(cfg)

saveRDS(hei_ready, here::here("data_processed", "hei_input_ready.rds"))
