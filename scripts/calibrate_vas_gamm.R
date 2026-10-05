# Small, explicitly synthetic coverage diagnostic. Not formal calibration approval.
args <- commandArgs(trailingOnly = TRUE)
root <- args[1]
out <- args[2]
nsim <- as.integer(args[3])
if (dir.exists(out)) {
  stop("Refuse to overwrite output")
}
dir.create(out, recursive = TRUE)
source(file.path(root, "R/vas_models.R"))
suppressPackageStartupMessages(library(mgcv))
set.seed(918521)
results <- data.frame()
for (scenario in c("flat_complete", "linear_random_missing", "curved_dropout")) {
  for (rep in seq_len(nsim)) {
    n <- 40
    grid <- 1:20
    true_mean <- if (scenario == "flat_complete") {
      rep(4, 20)
    } else if (scenario == "linear_random_missing") {
      2 + .15 * grid
    } else {
      2 + .5 * grid - .02 * grid^2
    }
    true_derivative <- if (scenario == "flat_complete") {
      rep(0, 20)
    } else if (scenario == "linear_random_missing") {
      rep(.15, 20)
    } else {
      .5 - .04 * grid
    }
    d <- do.call(
      rbind,
      lapply(seq_len(n), function(i) {
        error <- as.numeric(arima.sim(list(ar = .6), n = 20, sd = .3))
        vals <- true_mean + rnorm(1, 0, .5) + error
        z <- data.frame(
          subject_id = paste0("synthetic_", i),
          time_min = grid,
          vas = vals
        )
        if (scenario == "linear_random_missing") {
          z <- z[runif(20) > .15, ]
        }
        if (scenario == "curved_dropout") {
          z <- z[z$time_min <= sample(12:20, 1), ]
        }
        z
      })
    )
    warnings <- character()
    z <- tryCatch(
      withCallingHandlers(
        {
          fit <- fit_vas_gamm(d, 6, TRUE)
          matrices <- prediction_matrices(fit, grid)
          bands <- simultaneous_band(matrices$dx, coef(fit$gam), fit$gam$Vp, 1000)
          covered <- bands$lower <= true_derivative & bands$upper >= true_derivative
          data.frame(
            scenario = scenario,
            replicate = rep,
            success = TRUE,
            simultaneous_coverage = all(covered),
            boundary_coverage = all(covered[c(1, 20)]),
            pointwise_coverage = mean(covered),
            maximum_derivative_bias = max(abs(bands$estimate - true_derivative)),
            false_positive_flat = if (scenario == "flat_complete") {
              any(bands$lower > 0 | bands$upper < 0)
            } else {
              NA
            },
            error = ""
          )
        },
        warning = function(w) {
          warnings <<- c(warnings, conditionMessage(w))
          invokeRestart("muffleWarning")
        }
      ),
      error = function(e) {
        data.frame(
          scenario = scenario,
          replicate = rep,
          success = FALSE,
          simultaneous_coverage = NA,
          boundary_coverage = NA,
          pointwise_coverage = NA,
          maximum_derivative_bias = NA,
          false_positive_flat = NA,
          error = conditionMessage(e)
        )
      }
    )
    z$warnings <- paste(unique(warnings), collapse = "; ")
    results <- rbind(results, z)
    if (rep %% 10 == 0) {
      write.csv(
        results,
        file.path(out, "calibration_replicates.csv"),
        row.names = FALSE,
        na = ""
      )
      cat(scenario, rep, "/", nsim, "\n")
      flush.console()
    }
  }
}
write.csv(
  results,
  file.path(out, "calibration_replicates.csv"),
  row.names = FALSE,
  na = ""
)
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
writeLines(
  c(
    "Synthetic diagnostic; seed 918521; 40 subjects; CAR1 errors rho=.6; 1000 coefficient draws.",
    "Random dropout in this simulation is noninformative and does not resolve real E/T dropout.",
    "Only a small Monte Carlo assessment; not sufficient for declaring nominal coverage calibrated."
  ),
  file.path(out, "README.txt")
)
