# Synthetic checks for the additional full-curve reconstruction baseline.
g <- 1:10
w <- c(.5, rep(1, 8), .5)
test_y <- rbind(rep(3, 10), g / 2, rev(g) / 3)
stopifnot(
  person_constant_errors(test_y, w)[1] == 0,
  max(abs(person_constant_errors(test_y, w) - person_constant_errors(test_y + 7, w))) <
    1e-12
)
set.seed(701)
train_y <- matrix(runif(40 * 10, 0, 10), 40, 10)
before <- train_y
fp <- grid_fpca(train_y, g)
saved_mean <- fp$mean
error_a <- reconstruction_errors(fp, test_y, 2)
error_b <- reconstruction_errors(fp, test_y + 1, 2)
stopifnot(
  identical(fp$mean, saved_mean),
  identical(train_y, before),
  max(abs(saved_mean - colMeans(train_y))) < 1e-12,
  length(error_a) == 3,
  length(error_b) == 3
)
constant <- person_constant_errors(test_y, w)
for (k in 0:4) {
  stopifnot(all(is.finite(reconstruction_errors(fp, test_y, k) - constant)))
}
cat(
  'PASS: individual weighted constant baseline, training-only centering, paired full-curve losses\n'
)
