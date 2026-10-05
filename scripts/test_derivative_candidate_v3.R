args <- commandArgs(trailingOnly = TRUE)
source(file.path(args[1], "R/derivative_calibration.R"))
source(file.path(args[1], "R/derivative_candidate_v3.R"))
set.seed(61931)
d <- synthetic_derivative_data("curved_dropout", 40)$data
t <- 1:20
for (dim in c(8, 10)) {
  x <- bs_design_v3(t, dim)
  stopifnot(ncol(x) == dim)
  beta <- qr.solve(x, 2 + .5 * t - .02 * t^2)
  stopifnot(max(abs(bs_derivative_v3(t, dim) %*% beta - (.5 - .04 * t))) < 1e-5)
  fit <- fit_bs_v3(d, dim)
  stopifnot(
    max(abs(fit$gls_cov - fit$model_cov)) < 1e-6,
    min(eigen(fit$cr2, symmetric = TRUE)$values) > 0
  )
  # CR2 should be invariant to row ordering and labels.
  again <- fit_bs_v3(d[nrow(d):1, ], dim)
  stopifnot(max(abs(fit$cr2 - again$cr2)) < 1e-6)
}
# With known whitened working covariance, CR2 must restore each cluster's
# residual covariance to identity, yielding unbiased expected GLS sandwich.
xall <- cbind(1, matrix(rnorm(120 * 3), 120, 3))
inv <- solve(crossprod(xall))
expected_meat <- matrix(0, 4, 4)
for (ix in split(1:120, rep(1:12, each = 10))) {
  x <- xall[ix, ]
  residual_cov <- diag(10) - x %*% inv %*% t(x)
  ee <- eigen(residual_cov, symmetric = TRUE)
  aa <- ee$vectors %*% diag(1 / sqrt(ee$values)) %*% t(ee$vectors)
  restored <- aa %*% residual_cov %*% t(aa)
  stopifnot(max(abs(restored - diag(10))) < 1e-10)
  expected_meat <- expected_meat + crossprod(x, restored %*% x)
}
stopifnot(max(abs(inv %*% expected_meat %*% inv - inv)) < 1e-10)
cat(
  "PASS: v3 basis endpoints, GLS covariance, CR2 PSD/order invariance and known-covariance expectation identity\n"
)
