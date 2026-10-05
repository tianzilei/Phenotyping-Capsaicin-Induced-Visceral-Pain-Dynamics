args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
dir.create(out, recursive = TRUE)
.libPaths(c(
  'renv/library/reanalysis-20260926',
  'renv/library/sparse-fpca',
  .libPaths()
))
library(clubSandwich)
cfg <- jsonlite::fromJSON(
  'config/reanalysis_supplement_20260926_v1.json'
)$inference_calibration
set.seed(cfg$seed)
all <- data.frame()
for (scenario in cfg$scenarios) {
  n <- if (scenario == 'unbalanced15') 15 else 40
  for (rep in seq_len(cfg$replicates_per_scenario)) {
    d <- expand.grid(id = seq_len(n), block = 1:4)
    if (scenario != 'balanced40') {
      keep <- unlist(lapply(seq_len(n), function(i) {
        ix <- which(d$id == i)
        sample(ix, sample(2:4, 1))
      }))
      d <- d[sort(keep), ]
    }
    d$x <- rnorm(n)[d$id] + .2 * d$block + rnorm(nrow(d))
    common <- rnorm(n)
    d$y <- common[d$id] + .2 * d$block + (.5 + .1 * d$block) * rnorm(nrow(d))
    fit <- lm(y ~ x + factor(id) + factor(block), d)
    result <- tryCatch(
      coef_test(fit, vcov = 'CR2', cluster = d$id, test = 'Satterthwaite'),
      error = identity
    )
    ok <- !inherits(result, 'error')
    all <- rbind(
      all,
      data.frame(
        scenario = scenario,
        replicate = rep,
        success = ok,
        p = if (ok) result['x', 'p_Satt'] else NA,
        df = if (ok) result['x', 'df_Satt'] else NA
      )
    )
    if (rep %% 100 == 0) {
      write.csv(all, file.path(out, 'replicates.csv'), row.names = FALSE)
      cat(scenario, rep, '\n')
      flush.console()
    }
  }
}
summary <- do.call(
  rbind,
  lapply(split(all, all$scenario), function(z) {
    valid <- is.finite(z$p)
    n <- sum(valid)
    k <- sum(z$p[valid] < .05)
    ci <- binom.test(k, n)$conf.int
    data.frame(
      scenario = z$scenario[1],
      attempted = nrow(z),
      successful = n,
      type1 = k / n,
      mc_lower = ci[1],
      mc_upper = ci[2],
      median_df = median(z$df[valid]),
      status = 'synthetic_null_calibration_not_signal_validation'
    )
  })
)
write.csv(summary, file.path(out, 'summary.csv'), row.names = FALSE)
writeLines(capture.output(sessionInfo()), file.path(out, 'sessionInfo.txt'))
