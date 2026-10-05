# Scheduling adapter only: evaluate the unchanged worker for one original index.
# Preserve the complete source snapshot and the single documented loop substitution.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 9) {
  stop("Expected base worker arguments plus replicate index")
}
script <- readLines(
  file.path(args[1], "scripts/run_derivative_bootstrap_v4.R"),
  warn = FALSE
)
target <- "for(rep in seq_len(nsim)) {"
if (sum(script == target) != 1) {
  stop("Worker loop contract changed")
}
script[script == target] <- "for(rep in as.integer(args[9])) {"
eval(parse(text = script), envir = .GlobalEnv)
