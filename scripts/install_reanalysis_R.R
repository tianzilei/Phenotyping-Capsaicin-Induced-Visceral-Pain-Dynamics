lib <- file.path(getwd(), 'renv/library/reanalysis-20260926')
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
install.packages(
  'clubSandwich',
  lib = lib,
  repos = 'https://cloud.r-project.org',
  type = 'binary'
)
