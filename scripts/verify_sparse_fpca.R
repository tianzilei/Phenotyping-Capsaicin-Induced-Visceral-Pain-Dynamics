args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
.libPaths(c('renv/library/sparse-fpca', .libPaths()))
d <- read.csv('08_outputs/provisional_vas_20260916T144537Z_11f54777/vas_long.csv')
tab <- read.csv(file.path(out, 'eigenvalues.csv'))
support <- read.csv(file.path(out, 'joint_observation_support.csv'))
for (end in c(20, 10)) {
  label <- paste0('sparse_1_', end)
  f <- readRDS(file.path(out, paste0(label, '_model_private.rds')))
  # Direct comparison of every input minute/value with original observed rows.
  obs <- d[d$status == 'observed' & d$time_min <= end, ]
  groups <- split(obs, as.character(obs$subject_id), drop = TRUE)
  stopifnot(length(f$inputData$Ly) == length(groups))
  for (i in seq_along(groups)) {
    z <- groups[[i]][order(groups[[i]]$time_min), ]
    stopifnot(
      isTRUE(all.equal(as.numeric(z$time_min), as.numeric(f$inputData$Lt[[i]]))),
      isTRUE(all.equal(as.numeric(z$vas), as.numeric(f$inputData$Ly[[i]])))
    )
  }
  vals <- eigen(f$smoothedCov, symmetric = TRUE, only.values = TRUE)$values
  vals <- vals[vals > 0]
  expected <- cumsum(vals)[1:4] / sum(vals)
  stopifnot(max(abs(expected - tab$cumulative_fve[tab$interval == label])) < 1e-12)
  s <- support[support$interval == label, ]
  for (i in seq_len(nrow(s))) {
    expected_n <- sum(vapply(
      groups,
      function(z) all(c(s$time_a[i], s$time_b[i]) %in% z$time_min),
      logical(1)
    ))
    stopifnot(s$n_joint[i] == expected_n)
  }
}
cat(
  'Verified actual model inputs, complete positive-spectrum FVE denominator and all 500 joint-support cells.\n'
)
