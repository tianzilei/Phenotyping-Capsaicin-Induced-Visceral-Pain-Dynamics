.libPaths(c('renv/library/sparse-fpca', .libPaths()))
source('R/sparse_fpca.R')
# Synthetic ingestion preserves time gaps, zeros and singleton subjects.
d <- data.frame(
  subject_id = c('a', 'a', 'a', 'a', 'b'),
  time_min = c(1, 3, 4, 5, 2),
  vas = c(0, 2, NA, NA, 1),
  status = c('observed', 'observed', 'termination_E', 'post_termination', 'observed')
)
before <- d
i <- sparse_input(d, c(1, 5))
stopifnot(
  identical(i$Lt$a, c(1, 3)),
  identical(i$Ly$a, c(0, 2)),
  length(i$Ly$b) == 1,
  identical(d, before)
)
stopifnot(inherits(
  try(sparse_input(rbind(d, d[1, ]), c(1, 5)), silent = TRUE),
  'try-error'
))
# Span comparisons must be invariant to column scaling and basis rotation.
g <- 1:5
a <- list(workGrid = g, phi = cbind(rep(1, 5), g))
b <- list(workGrid = g, phi = a$phi %*% matrix(c(3, 1, -2, 4), 2))
stopifnot(sparse_angle(a, b, 2) < 1e-5)
# JSON integer bandwidths must be safely normalized at the Rcpp boundary.
cfg <- jsonlite::fromJSON('config/sparse_fpca_v1.json', simplifyVector = FALSE)
set.seed(37)
input <- list(Lt = rep(list(1:20), 216), Ly = lapply(1:216, function(i) rnorm(20)))
fit <- sparse_fit(input, cfg$options)
check_sparse_fit(fit, 216)
cat('Synthetic ingestion and weighted-subspace tests passed.\n')
