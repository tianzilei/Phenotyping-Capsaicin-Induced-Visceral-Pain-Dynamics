# Implemented provisional estimators. No imputation and no phenotype labels.
fit_vas_gamm <- function(d, k = 6, correlated = TRUE) {
  d <- d[order(d$subject_id, d$time_min), ]
  d$subject_id <- factor(d$subject_id)
  args <- list(
    formula = vas ~ s(time_min, bs = "cr", k = k),
    data = d,
    random = list(subject_id = ~1),
    method = "REML",
    control = nlme::lmeControl(msMaxIter = 150, niterEM = 30)
  )
  if (correlated) {
    args$correlation <- nlme::corCAR1(form = ~ time_min | subject_id)
  }
  do.call(mgcv::gamm, args)
}

prediction_matrices <- function(fit, grid) {
  h <- 1e-4
  lo <- pmax(min(grid), grid - h)
  hi <- pmin(max(grid), grid + h)
  x <- predict(fit$gam, data.frame(time_min = grid), type = "lpmatrix")
  dx <- (predict(fit$gam, data.frame(time_min = hi), type = "lpmatrix") -
    predict(fit$gam, data.frame(time_min = lo), type = "lpmatrix")) /
    (hi - lo)
  list(x = x, dx = dx)
}

simultaneous_band <- function(mat, beta, covariance, draws = 5000, level = .95) {
  estimate <- as.vector(mat %*% beta)
  se <- sqrt(pmax(0, rowSums((mat %*% covariance) * mat)))
  if (any(!is.finite(se)) || any(se <= 0)) {
    stop("Nonpositive prediction SE")
  }
  eig <- eigen(covariance, symmetric = TRUE)
  if (min(eig$values) < -1e-7 * max(1, max(eig$values))) {
    stop("Invalid coefficient covariance")
  }
  delta <- eig$vectors %*%
    (sqrt(pmax(0, eig$values)) *
      matrix(rnorm(length(beta) * draws), nrow = length(beta)))
  maxima <- apply(abs((mat %*% delta) / se), 2, max)
  critical <- as.numeric(quantile(maxima, level))
  data.frame(
    estimate = estimate,
    se = se,
    lower = estimate - critical * se,
    upper = estimate + critical * se,
    critical = critical
  )
}

resample_subjects <- function(d) {
  ids <- unique(as.character(d$subject_id))
  sampled <- sample(ids, length(ids), replace = TRUE)
  result <- do.call(
    rbind,
    lapply(seq_along(sampled), function(i) {
      z <- d[as.character(d$subject_id) == sampled[i], ]
      z$subject_id <- paste0("bootstrap_", i)
      z
    })
  )
  result$subject_id <- factor(result$subject_id)
  result
}

complete_matrix <- function(d, grid) {
  groups <- split(d, d$subject_id, drop = TRUE)
  selected <- groups[vapply(groups, function(z) all(grid %in% z$time_min), logical(1))]
  if (length(selected) < 5) {
    stop("Fewer than five complete trajectories")
  }
  y <- t(vapply(
    selected,
    function(z) z$vas[match(grid, z$time_min)],
    numeric(length(grid))
  ))
  if (any(!is.finite(y))) {
    stop("Nonfinite complete trajectory")
  }
  y
}

grid_fpca <- function(y, grid, max_components = 4) {
  # Trapezoidal quadrature: eigenfunctions are orthonormal under integral inner product.
  weights <- c(
    diff(grid)[1] / 2,
    (head(diff(grid), -1) + tail(diff(grid), -1)) / 2,
    tail(diff(grid), 1) / 2
  )
  mu <- colMeans(y)
  centered <- sweep(y, 2, mu)
  weighted <- sweep(centered, 2, sqrt(weights), "*")
  decomposition <- svd(
    weighted,
    nu = min(max_components, nrow(y) - 1),
    nv = min(max_components, nrow(y) - 1)
  )
  total <- sum(decomposition$d^2)
  if (total <= 1e-12) {
    stop("No between-trajectory variation for FPCA")
  }
  m <- min(max_components, nrow(y) - 1, ncol(y))
  phi <- sweep(decomposition$v[, seq_len(m), drop = FALSE], 1, sqrt(weights), "/")
  scores <- weighted %*% decomposition$v[, seq_len(m), drop = FALSE]
  # Deterministic display orientation only, not a physiological interpretation.
  for (j in seq_len(m)) {
    if (phi[which.max(abs(phi[, j])), j] < 0) {
      phi[, j] <- -phi[, j]
      scores[, j] <- -scores[, j]
    }
  }
  list(
    mean = mu,
    phi = phi,
    scores = scores,
    weights = weights,
    values = decomposition$d[seq_len(m)]^2 / (nrow(y) - 1),
    fve = decomposition$d[seq_len(m)]^2 / total
  )
}

axis_match <- function(reference, candidate) {
  # Exhaustive one-to-one matching; at most 4! possibilities.
  permutations <- function(v) {
    if (length(v) == 1) {
      return(matrix(v, nrow = 1))
    }
    do.call(rbind, lapply(v, function(x) cbind(x, permutations(v[v != x]))))
  }
  inner <- crossprod(reference$phi, reference$weights * candidate$phi)
  perms <- permutations(seq_len(ncol(inner)))
  objective <- apply(perms, 1, function(p) sum(abs(inner[cbind(seq_along(p), p)])))
  perm <- perms[which.max(objective), ]
  list(
    permutation = perm,
    correlation = abs(inner[cbind(seq_along(perm), perm)]),
    sign = sign(inner[cbind(seq_along(perm), perm)])
  )
}
