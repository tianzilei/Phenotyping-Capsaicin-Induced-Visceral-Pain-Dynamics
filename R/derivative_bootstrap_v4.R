fit_bootstrap_curve <- function(d) {
  d <- d[order(d$subject_id, d$time_min), ]
  d$subject_id <- factor(d$subject_id)
  x <- bs_design_v3(d$time_min, 8)
  for (j in 2:8) {
    d[[paste0("b", j - 1)]] <- x[, j]
  }
  fit <- nlme::lme(
    vas ~ b1 + b2 + b3 + b4 + b5 + b6 + b7,
    random = ~ 1 | subject_id,
    correlation = nlme::corCAR1(form = ~ time_min | subject_id),
    data = d,
    method = "REML",
    control = nlme::lmeControl(msMaxIter = 150, niterEM = 30)
  )
  dx <- bs_derivative_v3(1:20, 8)
  se <- sqrt(rowSums((dx %*% vcov(fit)) * dx))
  estimate <- as.vector(dx %*% nlme::fixef(fit))
  if (any(!is.finite(se)) || any(se <= 0) || any(!is.finite(estimate))) {
    stop("Invalid fit")
  }
  list(estimate = estimate, se = se, beta = nlme::fixef(fit), cov = vcov(fit))
}

bootstrap_derivative_bands <- function(original, estimates, ses, level = .95) {
  if (
    !identical(dim(estimates), dim(ses)) ||
      ncol(estimates) != length(original$estimate) ||
      nrow(estimates) < 2 ||
      any(!is.finite(estimates)) ||
      any(!is.finite(ses)) ||
      any(ses <= 0)
  ) {
    stop("Invalid bootstrap draws")
  }
  bias <- colMeans(estimates) - original$estimate
  make <- function(center, reference) {
    maxima <- apply(abs(sweep(estimates, 2, reference, "-") / ses), 1, max)
    critical <- as.numeric(quantile(maxima, level, type = 7))
    data.frame(
      estimate = center,
      se = original$se,
      lower = center - critical * original$se,
      upper = center + critical * original$se,
      critical = critical,
      bias = bias
    )
  }
  list(
    subject_bootstrap_t = make(original$estimate, original$estimate),
    subject_bootstrap_bias_corrected_t = make(
      original$estimate - bias,
      colMeans(estimates)
    )
  )
}
