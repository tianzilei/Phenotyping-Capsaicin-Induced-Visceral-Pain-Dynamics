residual_metrics <- function(t, y, degree) {
  if (anyDuplicated(t) || any(!is.finite(y))) {
    stop('Invalid series')
  }
  order <- order(t)
  t <- t[order]
  y <- y[order]
  x <- outer(t - mean(t), 0:degree, '^')
  fit <- lm.fit(x, y)
  if (fit$rank != ncol(x) || length(y) <= ncol(x)) {
    stop('Insufficient trend rank')
  }
  e <- fit$residuals
  adj <- which(diff(t) == 1)
  c(
    n = length(y),
    pairs = length(adj),
    residual_variance = sum(e^2) / (length(y) - ncol(x)),
    residual_mssd = if (length(adj)) mean((e[adj + 1] - e[adj])^2) else NA,
    raw_mssd = if (length(adj)) mean((y[adj + 1] - y[adj])^2) else NA
  )
}

segment_integrals <- function(t, y) {
  a <- head(t, -1)
  h <- diff(t)
  v <- head(y, -1)
  d <- diff(y)
  c(
    area = sum(h * (v + d / 2)),
    moment = sum(h * (a * v + (a * d + h * v) / 2 + h * d / 3))
  )
}

burden_metrics <- function(t, y) {
  if (length(t) != length(y) || any(diff(t) != 1) || any(!is.finite(y)) || any(y < 0)) {
    stop('Complete consecutive nonnegative series required')
  }
  total <- segment_integrals(t, y)
  mid <- mean(range(t))
  late_t <- sort(unique(c(mid, t[t > mid])))
  late_y <- approx(t, y, xout = late_t)$y
  late <- segment_integrals(late_t, late_y)['area']
  c(
    auc = unname(total['area']),
    time_centroid = if (total['area'] > 0) {
      unname(total['moment'] / total['area'])
    } else {
      NA
    },
    late_area_fraction = if (total['area'] > 0) unname(late / total['area']) else NA,
    first_observed_peak_minute = t[which.max(y)]
  )
}

modified_band_depth <- function(y, t) {
  if (nrow(y) < 2 || any(!is.finite(y))) {
    stop('Invalid complete curves')
  }
  n <- nrow(y)
  denom <- choose(n, 2)
  w <- c(
    diff(t)[1] / 2,
    (head(diff(t), -1) + tail(diff(t), -1)) / 2,
    tail(diff(t), 1) / 2
  )
  depth <- vapply(
    seq_len(n),
    function(i) {
      less <- colSums(sweep(y, 2, y[i, ], '<'))
      greater <- colSums(sweep(y, 2, y[i, ], '>'))
      sum(w * (1 - (choose(less, 2) + choose(greater, 2)) / denom)) / sum(w)
    },
    numeric(1)
  )
  cutoff <- sort(depth, decreasing = TRUE)[ceiling(n / 2)]
  central <- depth >= cutoff - 1e-12
  list(
    depth = depth,
    central = central,
    deepest = which.max(depth),
    lower = apply(y[central, , drop = FALSE], 2, min),
    upper = apply(y[central, , drop = FALSE], 2, max)
  )
}
