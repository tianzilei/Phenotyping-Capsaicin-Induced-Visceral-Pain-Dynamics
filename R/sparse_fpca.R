# Actual fdapace adapter; no filled individual trajectories.
sparse_input <- function(d, interval) {
  if (anyDuplicated(d[c('subject_id', 'time_min')])) {
    stop('Duplicate subject-minute')
  }
  observed <- d[
    d$status == 'observed' & d$time_min >= interval[1] & d$time_min <= interval[2],
  ]
  if (any(!is.finite(observed$vas))) {
    stop('Invalid observed VAS')
  }
  groups <- split(observed, as.character(observed$subject_id), drop = TRUE)
  groups <- lapply(groups, function(z) z[order(z$time_min), ])
  list(
    ids = names(groups),
    Ly = lapply(groups, function(z) z$vas),
    Lt = lapply(groups, function(z) z$time_min)
  )
}

sparse_fit <- function(input, options) {
  if (!length(input$Ly) || length(input$Ly) != length(input$Lt)) {
    stop('Invalid input lists')
  }
  # fdapace Rcpp mapped vectors require doubles even for integer minute grids.
  options$userBwMu <- as.numeric(options$userBwMu)
  options$userBwCov <- as.numeric(options$userBwCov)
  fdapace::FPCA(lapply(input$Ly, as.numeric), lapply(input$Lt, as.numeric), options)
}

weighted_span <- function(phi, grid, k) {
  w <- c(
    diff(grid)[1] / 2,
    (head(diff(grid), -1) + tail(diff(grid), -1)) / 2,
    tail(diff(grid), 1) / 2
  )
  z <- sqrt(w) * phi[, seq_len(k), drop = FALSE]
  q <- qr(z)
  if (q$rank < k) {
    stop('Rank deficient subspace')
  }
  qr.Q(q)[, seq_len(k), drop = FALSE]
}

sparse_angle <- function(a, b, k) {
  if (max(abs(a$workGrid - b$workGrid)) > 1e-10) {
    stop('Different grids')
  }
  x <- weighted_span(a$phi, a$workGrid, k)
  y <- weighted_span(b$phi, b$workGrid, k)
  max(acos(pmin(1, pmax(0, svd(crossprod(x, y), nu = 0, nv = 0)$d)))) * 180 / pi
}

sparse_fve <- function(fit) {
  vals <- eigen(fit$smoothedCov, symmetric = TRUE, only.values = TRUE)$values
  positive <- vals[vals > 0]
  cumsum(positive)[seq_len(ncol(fit$phi))] / sum(positive)
}

check_sparse_fit <- function(fit, n, k = 4) {
  stopifnot(
    ncol(fit$phi) == k,
    nrow(fit$xiEst) == n,
    all(is.finite(fit$mu)),
    all(is.finite(fit$phi)),
    all(is.finite(fit$xiEst)),
    all(fit$lambda > 0),
    is.finite(fit$sigma2),
    fit$sigma2 >= 0,
    min(eigen(fit$fittedCov, symmetric = TRUE, only.values = TRUE)$values) > -1e-7
  )
  invisible(TRUE)
}
