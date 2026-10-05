# Standalone candidate: unpenalized cubic B-splines, no natural boundary constraint.
# This file does not change the production GAMM estimator.
bs_design <- function(t) {
  cbind(
    `(Intercept)` = 1,
    splines::bs(
      t,
      knots = c(1 + 19 / 3, 1 + 38 / 3),
      Boundary.knots = c(1, 20),
      degree = 3,
      intercept = FALSE
    )
  )
}

bs_derivative <- function(t, h = 1e-4) {
  lo <- pmax(1, t - h)
  hi <- pmin(20, t + h)
  (bs_design(hi) - bs_design(lo)) / (hi - lo)
}

fit_bs_candidate <- function(d) {
  d <- d[order(d$subject_id, d$time_min), ]
  d$subject_id <- factor(d$subject_id)
  x <- bs_design(d$time_min)
  for (j in 2:ncol(x)) {
    d[[paste0("b", j - 1)]] <- x[, j]
  }
  fit <- nlme::lme(
    vas ~ b1 + b2 + b3 + b4 + b5,
    random = ~ 1 | subject_id,
    correlation = nlme::corCAR1(form = ~ time_min | subject_id),
    data = d,
    method = "REML",
    control = nlme::lmeControl(msMaxIter = 150, niterEM = 30)
  )
  ids <- levels(d$subject_id)
  g <- length(ids)
  bread <- matrix(0, ncol(x), ncol(x))
  meat <- bread
  for (id in ids) {
    ix <- which(d$subject_id == id)
    xi <- x[ix, , drop = FALSE]
    vi <- as.matrix(nlme::getVarCov(fit, individual = id, type = "marginal")[[1]])
    residual <- d$vas[ix] - as.vector(xi %*% nlme::fixef(fit))
    score <- crossprod(xi, solve(vi, residual))
    bread <- bread + crossprod(xi, solve(vi, xi))
    meat <- meat + tcrossprod(score)
  }
  inv <- solve(bread)
  robust <- inv %*% meat %*% inv * g / (g - 1)
  list(
    beta = nlme::fixef(fit),
    model_cov = vcov(fit),
    robust_cov = robust,
    df = g - 1,
    fit = fit,
    gls_cov = inv
  )
}

student_band <- function(mat, beta, covariance, draws = 2000, level = .95, df = Inf) {
  se <- sqrt(rowSums((mat %*% covariance) * mat))
  if (any(!is.finite(se)) || any(se <= 0)) {
    stop("Invalid band standard error")
  }
  ee <- eigen(covariance, symmetric = TRUE)
  if (min(ee$values) < -1e-7 * max(1, max(ee$values))) {
    stop("Invalid covariance")
  }
  delta <- ee$vectors %*%
    (sqrt(pmax(0, ee$values)) *
      matrix(rnorm(length(beta) * draws), nrow = length(beta)))
  if (is.finite(df)) {
    delta <- sweep(delta, 2, sqrt(rchisq(draws, df) / df), "/")
  }
  maxima <- apply(abs((mat %*% delta) / se), 2, max)
  critical <- as.numeric(quantile(maxima, level))
  estimate <- as.vector(mat %*% beta)
  data.frame(
    estimate = estimate,
    se = se,
    lower = estimate - critical * se,
    upper = estimate + critical * se,
    critical = critical
  )
}

synthetic_derivative_data <- function(scenario, n) {
  t <- 1:20
  mu <- switch(
    scenario,
    flat_complete = rep(4, 20),
    linear_random_missing = 2 + .15 * t,
    wave_dropout = 4 + sin(2 * pi * (t - 1) / 19),
    2 + .5 * t - .02 * t^2
  )
  truth <- switch(
    scenario,
    flat_complete = rep(0, 20),
    linear_random_missing = rep(.15, 20),
    wave_dropout = 2 * pi / 19 * cos(2 * pi * (t - 1) / 19),
    .5 - .04 * t
  )
  d <- do.call(
    rbind,
    lapply(seq_len(n), function(i) {
      y <- mu + rnorm(1, 0, .5) + as.numeric(arima.sim(list(ar = .6), n = 20, sd = .3))
      z <- data.frame(subject_id = paste0("synthetic_", i), time_min = t, vas = y)
      if (scenario == "linear_random_missing") {
        z <- z[runif(20) > .15, ]
      }
      if (scenario %in% c("curved_dropout", "wave_dropout")) {
        z <- z[t <= sample(12:20, 1), ]
      }
      if (scenario == "informative_dropout") {
        stop_at <- which(t > 10 & y < 4)
        if (length(stop_at)) z <- z[t <= stop_at[1], ]
      }
      z
    })
  )
  list(data = d, truth = truth)
}
