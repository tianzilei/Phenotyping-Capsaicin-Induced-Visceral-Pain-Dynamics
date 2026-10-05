# Project-local installation; never changes global R libraries.
lib <- file.path(getwd(), 'renv', 'library', 'sparse-fpca')
dir.create(lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(lib, .libPaths()))
options(repos = c(CRAN = 'https://cloud.r-project.org'), timeout = 120)
if (!requireNamespace('fdapace', quietly = TRUE)) {
  install.packages('fdapace', lib = lib, type = 'binary')
}
if (!requireNamespace('fdapace', quietly = TRUE)) {
  stop('fdapace installation unavailable')
}
cat('fdapace installed:', as.character(packageVersion('fdapace')), '\n')
write.csv(
  as.data.frame(installed.packages(lib.loc = lib)[,
    c('Package', 'Version', 'Built'),
    drop = FALSE
  ]),
  file.path(lib, 'installed_versions.csv'),
  row.names = FALSE
)
