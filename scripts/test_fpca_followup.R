source('R/vas_models.R')
source('R/fpca_followup.R')
grid <- c(1, 2, 4, 7)
y <- rbind(
  c(0, 1, 3, 2),
  c(2, 0, 4, 1),
  c(1, 3, 2, 5),
  c(3, 2, 0, 4),
  c(1, 1, 1, 1),
  c(4, 2, 3, 0)
)
fit <- grid_fpca(y, grid)
stopifnot(max(abs(crossprod(fit$phi, fit$weights * fit$phi) - diag(4))) < 1e-10)
stopifnot(max(abs(reconstruction_errors(fit, y, 4))) < 1e-10)
stopifnot(abs(sum(fit$weights) - 6) < 1e-10)
# A rotation changes individual axes, but not the leading two-dimensional span.
rot <- fit$phi
rot[, 1:2] <- fit$phi[, 1:2] %*% matrix(c(1, 1, -1, 1) / sqrt(2), 2)
stopifnot(principal_angle(fit$phi, rot, fit$weights, 2) < 1e-5)
stopifnot(abs(principal_angle(fit$phi, rot, fit$weights, 1) - 45) < 1e-8)
# Whole held-out curves do not refit the training mean.
fixed <- fit$mean
test <- matrix(rep(fixed + 2, 2), nrow = 2, byrow = TRUE)
stopifnot(max(abs(reconstruction_errors(fit, test, 0) - 2)) < 1e-10)
stopifnot(identical(fit$mean, fixed))
errs <- sapply(0:4, function(k) reconstruction_errors(fit, test, k))
stopifnot(all(apply(errs, 1, diff) <= 1e-10))
stopifnot(inherits(try(grid_fpca(matrix(1, 6, 4), grid), silent = TRUE), 'try-error'))
cat(
  'FPCA synthetic checks passed: weights, orthonormality, exact reconstruction, rotated subspaces, training-only mean, nested error, zero variance rejection.\n'
)
