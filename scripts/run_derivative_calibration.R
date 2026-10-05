args <- commandArgs(trailingOnly = TRUE)
root <- args[1]
out <- args[2]
nsim <- as.integer(args[3])
seed <- as.integer(args[4])
draws <- as.integer(args[5])
phase <- args[6]
source(file.path(root, "R/vas_models.R"))
source(file.path(root, "R/derivative_calibration.R"))
suppressPackageStartupMessages(library(mgcv))
cells <- data.frame(
  scenario = c(
    "flat_complete",
    "linear_random_missing",
    "curved_dropout",
    "wave_dropout",
    "informative_dropout",
    "curved_dropout"
  ),
  n = c(rep(40, 5), 216)
)
results <- data.frame()
points <- data.frame()
methods <- c("cr6_conditional", "cr10_conditional", "bs6_conditional", "bs6_cluster_t")
for (cell in seq_len(nrow(cells))) {
  for (rep in seq_len(nsim)) {
    scenario <- cells$scenario[cell]
    n <- cells$n[cell]
    set.seed(seed + cell * 100000 + rep)
    generated <- synthetic_derivative_data(scenario, n)
    d <- generated$data
    truth <- generated$truth
    bs_fit <- NULL
    for (m in seq_along(methods)) {
      method <- methods[m]
      warnings <- character()
      set.seed(seed + cell * 100000 + rep * 10 + m + 10000000)
      band <- tryCatch(
        withCallingHandlers(
          {
            if (m <= 2) {
              fit <- fit_vas_gamm(d, if (m == 1) 6 else 10, TRUE)
              student_band(
                prediction_matrices(fit, 1:20)$dx,
                coef(fit$gam),
                fit$gam$Vp,
                draws
              )
            } else {
              if (is.null(bs_fit)) {
                bs_fit <- fit_bs_candidate(d)
              }
              student_band(
                bs_derivative(1:20),
                bs_fit$beta,
                if (m == 3) bs_fit$model_cov else bs_fit$robust_cov,
                draws,
                df = if (m == 3) Inf else bs_fit$df
              )
            }
          },
          warning = function(w) {
            warnings <<- c(warnings, conditionMessage(w))
            invokeRestart("muffleWarning")
          }
        ),
        error = identity
      )
      ok <- !inherits(band, "error")
      if (ok) {
        covered <- band$lower <= truth & band$upper >= truth
        points <- rbind(
          points,
          data.frame(
            phase = phase,
            scenario = scenario,
            n = n,
            replicate = rep,
            method = method,
            time_min = 1:20,
            truth = truth,
            band,
            covered = covered
          )
        )
      }
      results <- rbind(
        results,
        data.frame(
          phase = phase,
          scenario = scenario,
          n = n,
          replicate = rep,
          method = method,
          success = ok,
          simultaneous_coverage = if (ok) all(covered) else FALSE,
          boundary_coverage = if (ok) all(covered[c(1, 20)]) else FALSE,
          interior_coverage = if (ok) all(covered[2:19]) else FALSE,
          pointwise_coverage = if (ok) mean(covered) else NA,
          mean_width = if (ok) mean(band$upper - band$lower) else NA,
          out_of_scale_generated_values = sum(d$vas < 0 | d$vas > 10),
          n_observations = nrow(d),
          warnings = paste(unique(warnings), collapse = "; "),
          error = if (ok) "" else conditionMessage(band)
        )
      )
    }
    if (rep %% 10 == 0 || rep == nsim) {
      write.csv(results, file.path(out, "replicates.csv"), row.names = FALSE, na = "")
      write.csv(points, file.path(out, "pointwise.csv"), row.names = FALSE, na = "")
      cat(format(Sys.time()), phase, scenario, "n", n, rep, "/", nsim, "\n")
      flush.console()
    }
  }
}
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
png(file.path(out, "coverage_diagnostics.png"), width = 1600, height = 1000, res = 150)
par(mfrow = c(2, 3), mar = c(4, 4, 3, 1))
colors <- c("#b4513f", "#b88b2c", "#438773", "#355e98")
for (cell in seq_len(nrow(cells))) {
  z <- subset(points, scenario == cells$scenario[cell] & n == cells$n[cell])
  plot(
    1:20,
    rep(0, 20),
    type = "n",
    ylim = c(-.12, .12),
    xlab = "Minute",
    ylab = "Mean derivative bias",
    main = paste(cells$scenario[cell], "n =", cells$n[cell])
  )
  abline(h = 0, lty = 2)
  for (m in seq_along(methods)) {
    zz <- z[z$method == methods[m], ]
    if (nrow(zz)) {
      lines(
        1:20,
        tapply(zz$estimate - zz$truth, zz$time_min, mean),
        col = colors[m],
        lwd = 2
      )
    }
  }
  if (cell == 1) {
    legend("bottomleft", legend = methods, col = colors, lty = 1, cex = .65, bty = "n")
  }
}
dev.off()
