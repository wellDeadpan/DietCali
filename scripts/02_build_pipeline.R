source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/utils_io.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/utils_check.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/derive_density.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/derive_servings.R")
source("/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/diet_index_ye/R/derive_foodgroups.R")

datpth <- "/restricted/projectnb/iloredcap/analysis/FFQ_analysis/Replication/NECS_replication/data/"

cfg  <- read_usda_config()

ffq <- read_data(paste0(datpth, "DQ scores for foods 10 November 2005 with import headers.xls"), skip=1)
nutrients <- read_data(paste0(datpth, "DQ file 9 Nov 2005.csv"))

hei_ready <- data$ffq %>%
  correct_ids(readr::read_csv("data_raw/id_crosswalk.csv")) %>%
  convert_to_servings(freq_vars = grep("05d$", names(.), value = TRUE),
                      conv_table = readr::read_csv("config/freq_to_servings.csv")) %>%
  derive_foodgroups() %>%
  derive_density("calories", c("HEItotfru05", "HEIveg05")) %>%
  calc_HEI2015(cfg)

saveRDS(hei_ready, "data_processed/hei_input_ready.rds")
