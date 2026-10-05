source('R/remaining_descriptives.R')
g <- 1:10
stopifnot(
  max(abs(residual_metrics(g, 2 + 3 * g, 1)[c('residual_variance', 'residual_mssd')])) <
    1e-20
)
stopifnot(residual_metrics(c(1, 2, 4, 5, 6, 7), c(1, 2, 2, 3, 4, 5), 1)['pairs'] == 4)
b <- burden_metrics(1:3, c(2, 2, 2))
stopifnot(b['auc'] == 4, b['time_centroid'] == 2, b['late_area_fraction'] == .5)
b <- burden_metrics(1:3, c(0, 1, 2))
stopifnot(
  abs(b['time_centroid'] - 7 / 3) < 1e-12,
  abs(b['late_area_fraction'] - .75) < 1e-12
)
stopifnot(is.na(burden_metrics(1:3, c(0, 0, 0))['time_centroid']))
stopifnot(inherits(try(burden_metrics(c(1, 3), c(0, 2)), silent = TRUE), 'try-error'))
y <- rbind(c(0, 0, 0), c(1, 1, 1), c(2, 2, 2), c(1, 1, 1))
d <- modified_band_depth(y, 1:3)
brute <- sapply(1:4, function(i) {
  mean(apply(combn(4, 2), 2, function(pair) {
    all(
      y[i, ] >= pmin(y[pair[1], ], y[pair[2], ]) &
        y[i, ] <= pmax(y[pair[1], ], y[pair[2], ])
    )
  }))
})
stopifnot(max(abs(d$depth - brute)) < 1e-12, all(d$central[c(2, 4)]))
# Known curved trend: a straight line leaves deterministic curvature in residuals.
linear <- residual_metrics(g, 2 + .1 * g^2, 1)
quadratic <- residual_metrics(g, 2 + .1 * g^2, 2)
stopifnot(linear['residual_variance'] > .1, quadratic['residual_variance'] < 1e-20)
# Engineering calibration under the exact model, not evidence for clinical assumptions.
set.seed(918012)
v <- replicate(
  500,
  residual_metrics(1:20, 3 + .05 * (1:20) + rnorm(20, sd = .5), 1)['residual_variance']
)
stopifnot(abs(mean(v) - .25) < .025)
cat('Remaining-descriptive synthetic tests passed.\n')
