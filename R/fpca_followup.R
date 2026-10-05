# Supplements for complete-trajectory weighted FPCA. No imputation.
principal_angle <- function(reference, candidate, weights, k) {
  a <- reference[, seq_len(k), drop = FALSE]
  b <- candidate[, seq_len(k), drop = FALSE]
  singular <- svd(crossprod(a, weights * b), nu = 0, nv = 0)$d
  max(acos(pmin(1, pmax(0, singular)))) * 180 / pi
}

reconstruction_errors <- function(train, test, k) {
  centered <- sweep(test, 2, train$mean)
  if (k == 0) {
    residual <- centered
  } else {
    phi <- train$phi[, seq_len(k), drop = FALSE]
    scores <- centered %*% (train$weights * phi)
    residual <- centered - scores %*% t(phi)
  }
  sqrt(rowSums(sweep(residual^2, 2, train$weights, '*')) / sum(train$weights))
}

summarize_range <- function(x) {
  x <- x[is.finite(x)]
  if (!length(x)) {
    return(c(median = NA, lower = NA, upper = NA))
  }
  c(
    median = median(x),
    lower = unname(quantile(x, .025)),
    upper = unname(quantile(x, .975))
  )
}
