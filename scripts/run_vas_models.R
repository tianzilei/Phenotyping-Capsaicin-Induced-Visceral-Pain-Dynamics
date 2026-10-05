args <- commandArgs(trailingOnly = TRUE)
root <- args[1]
out <- args[2]
seed <- as.integer(args[3])
B <- as.integer(args[4])
BF <- as.integer(args[5])
draws <- as.integer(args[6])
k_primary <- as.integer(args[7])
k_other <- as.integer(strsplit(args[8], ",")[[1]])
common_grid <- seq(as.integer(args[9]), as.integer(args[10]))
source(file.path(root, "R/vas_models.R"))
suppressPackageStartupMessages(library(mgcv))
set.seed(seed)
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
d <- read.csv(file.path(out, "vas_long.csv"), stringsAsFactors = FALSE)
d <- d[d$status == "observed", c("subject_id", "time_min", "vas")]
grid <- sort(unique(d$time_min))
if (length(grid) != 20 || any(grid != 1:20)) {
  stop("Expected observed support at minutes 1:20")
}
write_table <- function(x, name) {
  write.csv(x, file.path(out, name), row.names = FALSE, na = "")
}
progress <- function(message) {
  cat(format(Sys.time()), message, "\n")
  flush.console()
}
statuses <- data.frame(module = character(), status = character(), detail = character())
record <- function(module, status, detail = "") {
  statuses <<- rbind(
    statuses,
    data.frame(module = module, status = status, detail = detail)
  )
  write_table(statuses, "model_status.csv")
}
safe_fit <- function(data, k, correlated) {
  warnings <- character()
  value <- tryCatch(
    withCallingHandlers(fit_vas_gamm(data, k, correlated), warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    }),
    error = identity
  )
  list(fit = value, warnings = paste(unique(warnings), collapse = "; "))
}

progress("Fitting primary GAMM: CAR1, REML")
primary <- safe_fit(d, k_primary, TRUE)
if (inherits(primary$fit, "error")) {
  record("gamm_primary", "failed", conditionMessage(primary$fit))
} else {
  fit <- primary$fit
  matrices <- prediction_matrices(fit, grid)
  curve <- simultaneous_band(matrices$x, coef(fit$gam), fit$gam$Vp, draws)
  derivative <- simultaneous_band(matrices$dx, coef(fit$gam), fit$gam$Vp, draws)
  write_table(cbind(time_min = grid, curve), "gamm_curve.csv")
  write_table(
    cbind(
      time_min = grid,
      derivative,
      evidence = ifelse(
        derivative$lower > 0,
        "increasing",
        ifelse(derivative$upper < 0, "decreasing", "uncertain_not_plateau")
      )
    ),
    "gamm_derivatives.csv"
  )
  saveRDS(fit, file.path(out, "gamm_model_private.rds"))
  residual_data <- nlme::getData(fit$lme)
  conditional <- as.vector(predict(fit$lme, level = ncol(fit$lme$groups)))
  residual <- as.vector(residuals(fit$lme, type = "normalized"))
  write_table(
    data.frame(
      subject_id = residual_data$subject_id,
      time_min = residual_data$time_min,
      observed = residual_data$vas,
      conditional_fit = conditional,
      normalized_residual = residual
    ),
    "gamm_conditional_fits_private.csv"
  )
  adjacent <- do.call(
    rbind,
    lapply(
      split(data.frame(residual_data, residual = residual), residual_data$subject_id),
      function(z) {
        z <- z[order(z$time_min), ]
        ix <- which(diff(z$time_min) == 1)
        data.frame(a = z$residual[ix], b = z$residual[ix + 1])
      }
    )
  )
  rho <- as.numeric(coef(fit$lme$modelStruct$corStruct, unconstrained = FALSE))
  write_table(
    data.frame(
      n_subjects = length(unique(d$subject_id)),
      n_observations = nrow(d),
      k = k_primary,
      edf = sum(fit$gam$edf),
      car1 = rho,
      normalized_residual_adjacent_correlation = cor(adjacent$a, adjacent$b),
      n_adjacent_residual_pairs = nrow(adjacent),
      curve_outside_scale = sum(curve$estimate < 0 | curve$estimate > 10),
      conditional_outside_scale = sum(conditional < 0 | conditional > 10),
      warnings = primary$warnings
    ),
    "gamm_diagnostics.csv"
  )
  png(
    file.path(out, "gamm_curve_derivatives.png"),
    width = 1400,
    height = 1000,
    res = 150
  )
  par(mfrow = c(2, 1), mar = c(4, 4, 2, 1))
  for (j in 1:2) {
    z <- if (j == 1) curve else derivative
    plot(
      grid,
      z$estimate,
      type = "n",
      ylim = range(z$lower, z$upper),
      xlab = "Minute",
      ylab = if (j == 1) "VAS (0-10)" else "VAS / minute"
    )
    polygon(c(grid, rev(grid)), c(z$lower, rev(z$upper)), col = "#dae8ef", border = NA)
    lines(grid, z$estimate, lwd = 2, col = "#255b78")
    if (j == 2) {
      abline(h = 0, lty = 2)
    }
    title(
      if (j == 1) {
        "Provisional GAMM population curve"
      } else {
        "Derivative: 95% simultaneous coefficient band"
      }
    )
  }
  dev.off()
  png(file.path(out, "gamm_diagnostics.png"), width = 1400, height = 900, res = 150)
  par(mfrow = c(2, 2))
  plot(
    conditional,
    residual,
    pch = 16,
    cex = .3,
    xlab = "Conditional fitted VAS",
    ylab = "Normalized residual"
  )
  abline(h = 0, lty = 2)
  qqnorm(residual, pch = 16, cex = .3)
  qqline(residual)
  boxplot(
    residual ~ residual_data$time_min,
    xlab = "Actual minute",
    ylab = "Normalized residual"
  )
  plot(
    adjacent$a,
    adjacent$b,
    pch = 16,
    cex = .3,
    xlab = "Residual at t",
    ylab = "Residual at t+1 (no gaps)"
  )
  dev.off()
  record("gamm_primary", "completed_provisional", primary$warnings)
  boot_status <- data.frame()
  boot_curve <- matrix(NA_real_, B, length(grid))
  boot_deriv <- boot_curve
  for (b in seq_len(B)) {
    z <- safe_fit(resample_subjects(d), k_primary, TRUE)
    ok <- !inherits(z$fit, "error")
    if (ok) {
      pred <- prediction_matrices(z$fit, grid)
      boot_curve[b, ] <- as.vector(pred$x %*% coef(z$fit$gam))
      boot_deriv[b, ] <- as.vector(pred$dx %*% coef(z$fit$gam))
    }
    boot_status <- rbind(
      boot_status,
      data.frame(
        replicate = b,
        success = ok,
        detail = if (ok) z$warnings else conditionMessage(z$fit)
      )
    )
    if (b %% 10 == 0 || b == B) {
      write_table(boot_status, "gamm_bootstrap_status.csv")
      progress(paste("GAMM bootstrap", b, "/", B))
    }
  }
  write_table(
    data.frame(replicate = seq_len(B), boot_curve),
    "gamm_bootstrap_curves.csv"
  )
  write_table(
    data.frame(replicate = seq_len(B), boot_deriv),
    "gamm_bootstrap_derivatives.csv"
  )
  valid <- complete.cases(boot_deriv)
  if (sum(valid) >= max(20, .8 * B)) {
    qs <- t(apply(boot_deriv[valid, , drop = FALSE], 2, quantile, c(.025, .5, .975)))
    write_table(
      data.frame(
        time_min = grid,
        pointwise_lower = qs[, 1],
        median = qs[, 2],
        pointwise_upper = qs[, 3],
        n_success = sum(valid)
      ),
      "gamm_bootstrap_derivative_pointwise.csv"
    )
  }
  record(
    "gamm_subject_bootstrap",
    if (all(valid)) "completed_provisional" else "completed_with_failures",
    paste(
      sum(valid),
      "of",
      B,
      "successful; percentile summaries are pointwise, not simultaneous"
    )
  )
}

# All prescribed sensitivity fits are reported regardless of their result.
complete_ids <- rownames(complete_matrix(d, grid))
specs <- list(
  list(name = "independent_residual", data = d, k = k_primary, correlated = FALSE),
  list(
    name = "complete_1_20",
    data = d[d$subject_id %in% complete_ids, ],
    k = k_primary,
    correlated = TRUE
  ),
  list(
    name = "common_1_10",
    data = d[d$time_min %in% common_grid, ],
    k = k_primary,
    correlated = TRUE
  )
)
for (k in k_other) {
  specs[[length(specs) + 1]] <- list(
    name = paste0("k_", k),
    data = d,
    k = k,
    correlated = TRUE
  )
}
sens <- data.frame()
for (spec in specs) {
  progress(paste("Sensitivity", spec$name))
  z <- safe_fit(spec$data, spec$k, spec$correlated)
  if (inherits(z$fit, "error")) {
    record(paste0("gamm_", spec$name), "failed", conditionMessage(z$fit))
    next
  }
  g <- sort(unique(spec$data$time_min))
  p <- prediction_matrices(z$fit, g)
  band <- simultaneous_band(p$dx, coef(z$fit$gam), z$fit$gam$Vp, draws)
  sens <- rbind(
    sens,
    data.frame(
      specification = spec$name,
      time_min = g,
      n_subjects = length(unique(spec$data$subject_id)),
      curve = as.vector(p$x %*% coef(z$fit$gam)),
      derivative = band$estimate,
      lower = band$lower,
      upper = band$upper
    )
  )
  record(paste0("gamm_", spec$name), "completed_provisional", z$warnings)
}
write_table(sens, "gamm_sensitivity.csv")

for (g in list(grid, common_grid)) {
  label <- paste0("fpca_complete_", min(g), "_", max(g))
  progress(label)
  tryCatch(
    {
      y <- complete_matrix(d, g)
      fp <- grid_fpca(y, g)
      m <- ncol(fp$phi)
      write_table(
        data.frame(time_min = g, mean = fp$mean, fp$phi),
        paste0(label, "_functions.csv")
      )
      write_table(
        data.frame(subject_id = rownames(y), fp$scores),
        paste0(label, "_scores_private.csv")
      )
      write_table(
        data.frame(
          component = seq_len(m),
          eigenvalue = fp$values,
          FVE = fp$fve,
          cumulative_FVE = cumsum(fp$fve),
          n_subjects = nrow(y)
        ),
        paste0(label, "_eigenvalues.csv")
      )
      # Subject-held-out reconstruction: basis and mean fit in training folds only.
      folds <- sample(rep(1:5, length.out = nrow(y)))
      cv <- data.frame()
      for (fold in 1:5) {
        train <- grid_fpca(y[folds != fold, , drop = FALSE], g)
        test <- y[folds == fold, , drop = FALSE]
        centered <- sweep(test, 2, train$mean)
        score <- centered %*% (train$weights * train$phi)
        for (j in seq_len(m)) {
          reconstructed <- score[, seq_len(j), drop = FALSE] %*%
            t(train$phi[, seq_len(j), drop = FALSE])
          errors <- sqrt(
            rowSums(sweep((centered - reconstructed)^2, 2, train$weights, "*")) /
              sum(train$weights)
          )
          cv <- rbind(
            cv,
            data.frame(
              subject_id = rownames(test),
              fold = fold,
              components = j,
              weighted_rmse = errors
            )
          )
        }
      }
      write_table(cv, paste0(label, "_heldout_reconstruction_private.csv"))
      stability <- data.frame()
      bootstat <- data.frame()
      for (b in seq_len(BF)) {
        z <- tryCatch(
          grid_fpca(
            y[sample(seq_len(nrow(y)), nrow(y), replace = TRUE), , drop = FALSE],
            g
          ),
          error = identity
        )
        ok <- !inherits(z, "error")
        bootstat <- rbind(
          bootstat,
          data.frame(
            replicate = b,
            success = ok,
            detail = if (ok) "" else conditionMessage(z)
          )
        )
        if (ok) {
          matched <- axis_match(fp, z)
          angles <- svd(crossprod(fp$phi, fp$weights * z$phi), nu = 0, nv = 0)$d
          stability <- rbind(
            stability,
            data.frame(
              replicate = b,
              component = seq_len(m),
              matched_component = matched$permutation,
              absolute_inner_product = matched$correlation,
              matched_eigenvalue = z$values[matched$permutation],
              maximum_subspace_angle_deg = max(acos(pmin(1, pmax(0, angles)))) *
                180 /
                pi
            )
          )
        }
      }
      write_table(stability, paste0(label, "_stability.csv"))
      write_table(bootstat, paste0(label, "_bootstrap_status.csv"))
      # Redundancy on exactly the same complete interval, observed peak only.
      metrics <- cbind(
        observed_mean = rowMeans(y),
        auc = as.vector(y %*% fp$weights),
        first_observed_peak_min = g[max.col(y, ties.method = "first")]
      )
      redundancy <- do.call(
        rbind,
        lapply(seq_len(m), function(j) {
          data.frame(
            component = j,
            metric = colnames(metrics),
            spearman = vapply(
              seq_len(ncol(metrics)),
              function(k) cor(fp$scores[, j], metrics[, k], method = "spearman"),
              numeric(1)
            ),
            n_subjects = nrow(y)
          )
        })
      )
      write_table(redundancy, paste0(label, "_redundancy.csv"))
      png(file.path(out, paste0(label, ".png")), width = 1400, height = 1000, res = 150)
      par(mfrow = c(2, 2), mar = c(4, 4, 3, 1))
      for (j in seq_len(m)) {
        curves <- cbind(
          fp$mean,
          fp$mean + 2 * sqrt(fp$values[j]) * fp$phi[, j],
          fp$mean - 2 * sqrt(fp$values[j]) * fp$phi[, j]
        )
        matplot(
          g,
          curves,
          type = "l",
          lty = c(1, 2, 2),
          col = c("black", "#2166ac", "#b2182b"),
          xlab = "Minute",
          ylab = "VAS",
          main = paste("PC", j, "FVE", round(100 * fp$fve[j], 1), "%")
        )
      }
      dev.off()
      record(
        label,
        "completed_provisional",
        paste(
          nrow(y),
          "complete trajectories; discretized functional PCA; no sparse PACE; held-out reconstruction uses full test curve, not prediction"
        )
      )
    },
    error = function(e) record(label, "failed", conditionMessage(e))
  )
}
progress("Model execution finished")
