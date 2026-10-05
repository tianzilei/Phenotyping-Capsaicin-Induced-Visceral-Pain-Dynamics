# Run explicitly from the repository root. No statistical analysis is executed.
args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", args[grepl("^--file=", args)])
root <- dirname(dirname(normalizePath(file_arg)))
setwd(root)
bootstrap_lib <- file.path(root, "renv", "bootstrap-library")
dir.create(bootstrap_lib, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(bootstrap_lib, .libPaths()))
options(repos = c(CRAN = "https://cloud.r-project.org"))
if (!requireNamespace("renv", quietly = TRUE)) {
  install.packages("renv", lib = bootstrap_lib)
}
if (file.exists("renv.lock")) {
  renv::restore(project = root, prompt = FALSE)
} else {
  renv::init(project = root, bare = TRUE, restart = FALSE)
  packages <- readLines("dependencies/r-packages.txt")
  renv::install(packages[nzchar(packages)])
  renv::snapshot(type = "all", prompt = FALSE)
}
cat(
  "R project dependencies ready. Commit the generated renv.lock and activation files.\n"
)
