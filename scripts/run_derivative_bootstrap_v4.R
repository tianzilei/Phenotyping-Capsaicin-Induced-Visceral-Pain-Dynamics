args <- commandArgs(trailingOnly = TRUE)
root <- args[1]
out <- args[2]
scenario <- args[3]
n <- as.integer(args[4])
nsim <- as.integer(args[5])
B <- as.integer(args[6])
seed <- as.integer(args[7])
draws <- as.integer(args[8])
source(file.path(root, "R/vas_models.R"))
source(file.path(root, "R/derivative_calibration.R"))
source(file.path(root, "R/derivative_candidate_v3.R"))
source(file.path(root, "R/derivative_bootstrap_v4.R"))
results <- data.frame()
points <- data.frame()
statuses <- data.frame()
safe <- function(expr) {
  warnings <- character()
  value <- tryCatch(
    withCallingHandlers(expr, warning = function(w) {
      warnings <<- c(warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    }),
    error = identity
  )
  list(value = value, warnings = paste(unique(warnings), collapse = "; "))
}
save_tables <- function() {
  write.csv(results, file.path(out, "replicates.csv"), row.names = FALSE, na = "")
  write.csv(points, file.path(out, "pointwise.csv"), row.names = FALSE, na = "")
  write.csv(
    statuses,
    file.path(out, "bootstrap_status.csv"),
    row.names = FALSE,
    na = ""
  )
}
for (rep in seq_len(nsim)) {
  set.seed(seed + rep)
  generated <- synthetic_derivative_data(scenario, n)
  d <- generated$data
  truth <- generated$truth
  main <- safe(fit_bootstrap_curve(d))
  original <- main$value
  bands <- list()
  valid <- 0L
  if (!inherits(original, "error")) {
    set.seed(seed + rep + 1000000)
    bands$model_coefficient <- student_band(
      bs_derivative_v3(1:20, 8),
      original$beta,
      original$cov,
      draws
    )
    est <- matrix(NA_real_, B, 20)
    ses <- est
    for (b in seq_len(B)) {
      set.seed(seed + rep * 10000 + b + 2000000)
      boot <- safe(fit_bootstrap_curve(resample_subjects(d)))
      ok <- !inherits(boot$value, "error")
      if (ok) {
        est[b, ] <- boot$value$estimate
        ses[b, ] <- boot$value$se
      }
      statuses <- rbind(
        statuses,
        data.frame(
          replicate = rep,
          bootstrap = b,
          success = ok,
          warnings = boot$warnings,
          error = if (ok) "" else conditionMessage(boot$value)
        )
      )
      if (b %% 50 == 0) {
        cat(
          format(Sys.time()),
          scenario,
          n,
          rep,
          "/",
          nsim,
          "bootstrap",
          b,
          "/",
          B,
          "\n"
        )
        flush.console()
      }
    }
    good <- apply(is.finite(est) & is.finite(ses) & ses > 0, 1, all)
    valid <- sum(good)
    if (valid >= ceiling(.98 * B)) {
      bands <- c(
        bands,
        bootstrap_derivative_bands(
          original,
          est[good, , drop = FALSE],
          ses[good, , drop = FALSE]
        )
      )
    }
  }
  for (method in c(
    "model_coefficient",
    "subject_bootstrap_t",
    "subject_bootstrap_bias_corrected_t"
  )) {
    band <- bands[[method]]
    ok <- !is.null(band)
    if (ok) {
      if (is.null(band$bias)) {
        band$bias <- NA_real_
      }
      covered <- band$lower <= truth & band$upper >= truth
      points <- rbind(
        points,
        data.frame(
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
        scenario = scenario,
        n = n,
        replicate = rep,
        method = method,
        success = ok,
        simultaneous_coverage = if (ok) all(covered) else FALSE,
        boundary_coverage = if (ok) all(covered[c(1, 20)]) else FALSE,
        interior_coverage = if (ok) all(covered[2:19]) else FALSE,
        mean_width = if (ok) mean(band$upper - band$lower) else NA,
        valid_bootstraps = valid,
        requested_bootstraps = B,
        out_of_scale = sum(d$vas < 0 | d$vas > 10),
        warnings = main$warnings,
        error = if (inherits(original, "error")) {
          conditionMessage(original)
        } else if (!ok) {
          "Insufficient valid bootstraps"
        } else {
          ""
        }
      )
    )
  }
  save_tables()
  cat(format(Sys.time()), scenario, n, rep, "/", nsim, "complete\n")
  flush.console()
}
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
