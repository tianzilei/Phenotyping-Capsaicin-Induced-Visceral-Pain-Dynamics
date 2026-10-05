args <- commandArgs(trailingOnly = TRUE)
source(file.path(args[1], "R/derivative_calibration.R"))
set.seed(69201)
t <- 1:20
beta <- qr.solve(bs_design(t), 2 + .5 * t - .02 * t^2)
# Polynomial reproduction tests both endpoints, not just an interior fit.
stopifnot(max(abs(bs_derivative(t) %*% beta - (.5 - .04 * t))) < 1e-5)
d <- synthetic_derivative_data("curved_dropout", 40)$data
fit <- fit_bs_candidate(d)
# Independently computed GLS bread must match nlme fixed-effect covariance.
stopifnot(max(abs(fit$gls_cov - fit$model_cov)) < 1e-6)
stopifnot(min(eigen(fit$robust_cov, symmetric = TRUE)$values) > -1e-10)
band <- student_band(bs_derivative(t), fit$beta, fit$robust_cov, 2000, df = fit$df)
stopifnot(all(is.finite(band$lower)), all(band$upper > band$lower))
# Subject labels and row order must not affect the fitted mean or sandwich.
shuffled <- d[nrow(d):1, ]
shuffled$subject_id <- paste0("renamed_", shuffled$subject_id)
again <- fit_bs_candidate(shuffled)
stopifnot(
  max(abs(fit$beta - again$beta)) < 1e-6,
  max(abs(fit$robust_cov - again$robust_cov)) < 1e-6
)
cat(
  "PASS: endpoint polynomial derivative, independent GLS covariance, PSD sandwich, finite t bands, subject label/order invariance\n"
)
