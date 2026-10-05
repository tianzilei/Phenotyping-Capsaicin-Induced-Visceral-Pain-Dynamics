# Second development version: flexible fixed basis and cluster leverage adjustment.
# Keep v2 unchanged for reproducibility of its failed wave scenario.
bs_design_v3 <- function(t, dimension = 8) {
  knots <- seq(1, 20, length.out = dimension - 2)[-c(1, dimension - 2)]
  cbind(
    `(Intercept)` = 1,
    splines::bs(
      t,
      knots = knots,
      Boundary.knots = c(1, 20),
      degree = 3,
      intercept = FALSE
    )
  )
}
bs_derivative_v3 <- function(t, dimension = 8, h = 1e-4) {
  lo <- pmax(1, t - h)
  hi <- pmin(20, t + h)
  (bs_design_v3(hi, dimension) - bs_design_v3(lo, dimension)) / (hi - lo)
}
fit_bs_v3 <- function(d, dimension = 8) {
  d <- d[order(d$subject_id, d$time_min), ]
  d$subject_id <- factor(d$subject_id)
  x <- bs_design_v3(d$time_min, dimension)
  for (j in 2:ncol(x)) {
    d[[paste0("b", j - 1)]] <- x[, j]
  }
  formula <- reformulate(paste0("b", 1:(dimension - 1)), response = "vas")
  fit <- nlme::lme(
    formula,
    random = ~ 1 | subject_id,
    correlation = nlme::corCAR1(form = ~ time_min | subject_id),
    data = d,
    method = "REML",
    control = nlme::lmeControl(msMaxIter = 150, niterEM = 30)
  )
  ids <- levels(d$subject_id)
  g <- length(ids)
  bread <- matrix(0, dimension, dimension)
  blocks <- list()
  for (id in ids) {
    ix <- which(d$subject_id == id)
    xi <- x[ix, , drop = FALSE]
    vi <- as.matrix(nlme::getVarCov(fit, individual = id, type = "marginal")[[1]])
    cholv <- t(chol(vi))
    xw <- forwardsolve(cholv, xi)
    ew <- forwardsolve(cholv, d$vas[ix] - as.vector(xi %*% nlme::fixef(fit)))
    bread <- bread + crossprod(xw)
    blocks[[id]] <- list(x = xw, e = ew)
  }
  inv <- solve(bread)
  meat1 <- matrix(0, dimension, dimension)
  meat2 <- meat1
  for (block in blocks) {
    score1 <- crossprod(block$x, block$e)
    residual_cov <- diag(nrow(block$x)) - block$x %*% inv %*% t(block$x)
    ee <- eigen(residual_cov, symmetric = TRUE)
    if (min(ee$values) < 1e-8) {
      stop("Unstable cluster leverage correction")
    }
    adjusted <- ee$vectors %*% ((1 / sqrt(ee$values)) * crossprod(ee$vectors, block$e))
    score2 <- crossprod(block$x, adjusted)
    meat1 <- meat1 + tcrossprod(score1)
    meat2 <- meat2 + tcrossprod(score2)
  }
  list(
    beta = nlme::fixef(fit),
    model_cov = vcov(fit),
    cr1 = inv %*% meat1 %*% inv * g / (g - 1),
    cr2 = inv %*% meat2 %*% inv,
    gls_cov = inv,
    df = g - 1,
    fit = fit
  )
}
