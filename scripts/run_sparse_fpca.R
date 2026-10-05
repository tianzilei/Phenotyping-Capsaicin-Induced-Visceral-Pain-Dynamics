args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
.libPaths(c('renv/library/sparse-fpca', .libPaths()))
source('R/sparse_fpca.R')
config_path <- if (length(args) >= 2) args[2] else 'config/sparse_fpca_v1.json'
cfg <- jsonlite::fromJSON(config_path, simplifyVector = FALSE)
options_fp <- cfg$options
stopifnot(as.character(packageVersion('fdapace')) == '0.6.0')
write_table <- function(x, name) {
  write.csv(x, file.path(out, name), row.names = FALSE, na = '')
}
warnings_log <- data.frame(context = character(), message = character())
capture_fit <- function(input, op, context) {
  withCallingHandlers(sparse_fit(input, op), warning = function(w) {
    warnings_log <<- rbind(
      warnings_log,
      data.frame(context = context, message = conditionMessage(w))
    )
    invokeRestart('muffleWarning')
  })
}
# Freeze/read configuration before generating synthetic data or reading real rows.
simulation <- data.frame()
set.seed(cfg$simulation$seed)
for (scenario in unlist(cfg$simulation$scenarios)) {
  for (rep in seq_len(cfg$simulation$repeats)) {
    n <- cfg$simulation$n_subjects
    g <- 1:20
    s1 <- runif(n, -sqrt(3), sqrt(3))
    s2 <- runif(n, -sqrt(3), sqrt(3))
    mean_true <- 4 + .5 * sin(2 * pi * (g - 1) / 19)
    y <- matrix(mean_true, n, 20, byrow = TRUE) +
      .8 * s1 +
      outer(.7 * s2, sqrt(2) * cos(pi * (g - 1) / 19)) +
      matrix(rnorm(n * 20, sd = .15), n)
    times <- if (scenario == 'random_sparse') {
      lapply(seq_len(n), function(i) sort(sample(g, 8)))
    } else {
      last <- if (scenario == 'independent_dropout') {
        sample(10:20, n, replace = TRUE)
      } else {
        pmax(7, pmin(20, round(15 - 3 * s1)))
      }
      lapply(last, seq_len)
    }
    input <- list(Lt = times, Ly = lapply(seq_len(n), function(i) y[i, times[[i]]]))
    fit <- tryCatch(
      capture_fit(input, options_fp, paste('simulation', scenario, rep)),
      error = identity
    )
    ok <- !inherits(fit, 'error')
    if (ok) {
      ok <- isTRUE(tryCatch(check_sparse_fit(fit, n), error = function(e) FALSE))
    }
    if (ok) {
      truth <- list(
        workGrid = fit$workGrid,
        phi = cbind(
          rep(1, length(fit$workGrid)),
          sqrt(2) * cos(pi * (fit$workGrid - 1) / 19)
        )
      )
      rmse <- sqrt(mean((fit$mu - (4 + .5 * sin(2 * pi * (fit$workGrid - 1) / 19)))^2))
      angle <- sparse_angle(fit, truth, 2)
    } else {
      rmse <- angle <- NA_real_
    }
    simulation <- rbind(
      simulation,
      data.frame(
        scenario = scenario,
        replicate = rep,
        success = ok,
        mean_rmse = rmse,
        leading2_angle_deg = angle,
        generated_out_of_bounds = sum(y < 0 | y > 10),
        detail = if (inherits(fit, 'error')) conditionMessage(fit) else ''
      )
    )
    write_table(simulation, 'simulation_results.csv')
    cat('simulation', scenario, rep, 'success', ok, '\n')
    flush.console()
  }
}
write_table(warnings_log, 'warnings.csv')
if (!all(simulation$success)) {
  stop('Synthetic engineering gate failed; real data not run')
}
d <- read.csv(file.path(cfg$input_run, 'vas_long.csv'), stringsAsFactors = FALSE)
summary <- stability <- sensitivity <- support <- data.frame()
for (interval in cfg$intervals) {
  interval <- unlist(interval)
  end <- interval[2]
  label <- paste0('sparse_1_', end)
  input <- sparse_input(d, interval)
  fit <- capture_fit(input, options_fp, label)
  check_sparse_fit(fit, length(input$Ly))
  saveRDS(fit, file.path(out, paste0(label, '_model_private.rds')))
  write_table(
    data.frame(subject_id = input$ids, n_observed = lengths(input$Ly), fit$xiEst),
    paste0(label, '_scores_private.csv')
  )
  write_table(
    data.frame(time_min = fit$workGrid, mean = fit$mu, fit$phi),
    paste0(label, '_functions.csv')
  )
  jsonlite::write_json(
    fit$optns,
    file.path(out, paste0(label, '_actual_options.json')),
    auto_unbox = TRUE,
    pretty = TRUE
  )
  cum <- sparse_fve(fit)
  summary <- rbind(
    summary,
    data.frame(
      interval = label,
      n_subjects = length(input$Ly),
      n_observations = sum(lengths(input$Ly)),
      k = 1:4,
      eigenvalue = fit$lambda,
      cumulative_fve = cum,
      sigma2 = fit$sigma2,
      bw_mean = fit$bwMu,
      bw_covariance = fit$bwCov
    )
  )
  for (a in seq.int(interval[1], end)) {
    for (b in seq.int(interval[1], end)) {
      support <- rbind(
        support,
        data.frame(
          interval = label,
          time_a = a,
          time_b = b,
          n_joint = sum(vapply(input$Lt, function(t) a %in% t && b %in% t, logical(1)))
        )
      )
    }
  }
  boot <- status <- data.frame()
  set.seed(cfg$bootstrap$seed + end)
  for (rep in seq_len(cfg$bootstrap$replicates)) {
    idx <- sample(seq_along(input$Ly), length(input$Ly), replace = TRUE)
    z <- tryCatch(
      {
        f <- capture_fit(
          list(Ly = input$Ly[idx], Lt = input$Lt[idx]),
          options_fp,
          paste(label, 'bootstrap', rep)
        )
        check_sparse_fit(f, length(idx))
        f
      },
      error = identity
    )
    ok <- !inherits(z, 'error')
    if (ok) {
      angles <- tryCatch(
        sapply(1:4, function(k) sparse_angle(fit, z, k)),
        error = identity
      )
      if (inherits(angles, 'error')) {
        z <- angles
        ok <- FALSE
      }
    }
    status <- rbind(
      status,
      data.frame(
        replicate = rep,
        success = ok,
        detail = if (ok) '' else conditionMessage(z)
      )
    )
    if (ok) {
      boot <- rbind(
        boot,
        data.frame(
          replicate = rep,
          k = 1:4,
          max_angle_deg = angles,
          cumulative_fve = sparse_fve(z)
        )
      )
    }
    if (rep %% 10 == 0) {
      cat(label, 'bootstrap', rep, '/', cfg$bootstrap$replicates, '\n')
      flush.console()
      write_table(status, paste0(label, '_bootstrap_status.csv'))
    }
  }
  write_table(boot, paste0(label, '_bootstrap.csv'))
  write_table(status, paste0(label, '_bootstrap_status.csv'))
  for (k in 1:4) {
    vals <- boot$max_angle_deg[boot$k == k]
    stability <- rbind(
      stability,
      data.frame(
        interval = label,
        k = k,
        successful = sum(status$success),
        attempted = nrow(status),
        success_gate = mean(status$success) >= cfg$bootstrap$minimum_success_fraction,
        median = if (length(vals)) median(vals) else NA,
        lower = if (length(vals)) quantile(vals, .025) else NA,
        upper = if (length(vals)) quantile(vals, .975) else NA
      )
    )
  }
  for (bw in cfg$bandwidth_sensitivity) {
    op <- options_fp
    op$userBwMu <- bw[[1]]
    op$userBwCov <- bw[[2]]
    z <- tryCatch(
      {
        f <- capture_fit(
          input,
          op,
          paste(label, 'sensitivity', paste(bw, collapse = '/'))
        )
        check_sparse_fit(f, length(input$Ly))
        f
      },
      error = identity
    )
    ok <- !inherits(z, 'error')
    for (k in 1:4) {
      sensitivity <- rbind(
        sensitivity,
        data.frame(
          interval = label,
          bw_mean = bw[[1]],
          bw_covariance = bw[[2]],
          k = k,
          success = ok,
          angle_from_primary = if (ok) sparse_angle(fit, z, k) else NA,
          cumulative_fve = if (ok) sparse_fve(z)[k] else NA,
          detail = if (ok) '' else conditionMessage(z)
        )
      )
    }
  }
  cat(label, 'finished\n')
  flush.console()
}
write_table(summary, 'eigenvalues.csv')
write_table(stability, 'stability_summary.csv')
write_table(sensitivity, 'bandwidth_sensitivity.csv')
write_table(support, 'joint_observation_support.csv')
write_table(warnings_log, 'warnings.csv')
png(file.path(out, 'sparse_fpca.png'), width = 1600, height = 1000, res = 150)
par(mfrow = c(2, 2), mar = c(4, 4, 3, 1))
for (label in unique(summary$interval)) {
  f <- readRDS(file.path(out, paste0(label, '_model_private.rds')))
  raw <- aggregate(
    vas ~ time_min,
    d[d$status == 'observed' & d$time_min <= max(f$workGrid), ],
    mean
  )
  plot(
    f$workGrid,
    f$mu,
    type = 'l',
    ylim = range(c(f$mu, raw$vas)),
    xlab = 'Minute',
    ylab = 'Working-model VAS mean',
    main = paste(label, 'bandwidth 2 min')
  )
  points(raw$time_min, raw$vas, pch = 16, cex = .7, col = '#2166ac')
  s <- stability[stability$interval == label, ]
  plot(
    s$k,
    s$median,
    type = 'b',
    ylim = c(0, 90),
    xaxt = 'n',
    xlab = 'Leading components',
    ylab = 'Maximum subspace angle (degrees)',
    main = 'Bootstrap median and 2.5-97.5 percentiles'
  )
  axis(1, 1:4)
  segments(s$k, s$lower, s$k, s$upper, col = '#2166ac', lwd = 2)
}
dev.off()
writeLines(capture.output(sessionInfo()), file.path(out, 'sessionInfo.txt'))
writeLines(
  capture.output(tools::Rd2txt(utils:::.getHelpFile(help(
    'FPCA',
    package = 'fdapace'
  )))),
  file.path(out, 'fdapace_help.txt')
)
