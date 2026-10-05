args <- commandArgs(trailingOnly = TRUE)
prior <- args[1]
out <- args[2]
B <- as.integer(args[3])
repeats <- as.integer(args[4])
folds_n <- as.integer(args[5])
seed <- as.integer(args[6])
source('R/vas_models.R')
source('R/fpca_followup.R')
write_table <- function(x, name) {
  write.csv(x, file.path(out, name), row.names = FALSE, na = '')
}
d <- read.csv(file.path(prior, 'vas_long.csv'), stringsAsFactors = FALSE)
d <- d[d$status == 'observed', ]
all_summary <- all_cv <- all_stability <- all_redundancy <- data.frame()
for (end in c(20, 10)) {
  g <- seq_len(end)
  label <- paste0('complete_1_', end)
  y <- complete_matrix(d, g)
  fp <- grid_fpca(y, g)
  old <- read.csv(file.path(prior, paste0('fpca_', label, '_eigenvalues.csv')))
  stopifnot(
    max(abs(fp$values - old$eigenvalue)) < 1e-9,
    max(abs(fp$fve - old$FVE)) < 1e-10
  )
  write_table(
    data.frame(subject_id = rownames(y), fp$scores),
    paste0(label, '_scores_private.csv')
  )
  write_table(
    data.frame(time_min = g, mean = fp$mean, fp$phi),
    paste0(label, '_functions.csv')
  )
  set.seed(seed + end)
  boot <- status <- data.frame()
  for (b in seq_len(B)) {
    z <- tryCatch(
      grid_fpca(
        y[sample(seq_len(nrow(y)), nrow(y), replace = TRUE), , drop = FALSE],
        g
      ),
      error = identity
    )
    ok <- !inherits(z, 'error')
    status <- rbind(
      status,
      data.frame(
        replicate = b,
        success = ok,
        detail = if (ok) '' else conditionMessage(z)
      )
    )
    if (ok) {
      matched <- axis_match(fp, z)
      for (k in 1:4) {
        boot <- rbind(
          boot,
          data.frame(
            replicate = b,
            k = k,
            cumulative_fve = sum(z$fve[1:k]),
            max_angle_deg = principal_angle(fp$phi, z$phi, fp$weights, k),
            matched_axis_inner = matched$correlation[k],
            matched_component = matched$permutation[k]
          )
        )
      }
    }
  }
  write_table(status, paste0(label, '_bootstrap_status.csv'))
  write_table(boot, paste0(label, '_bootstrap_stability.csv'))
  for (k in 1:4) {
    z <- boot[boot$k == k, ]
    for (metric in c('max_angle_deg', 'matched_axis_inner', 'cumulative_fve')) {
      s <- summarize_range(z[[metric]])
      all_stability <- rbind(
        all_stability,
        data.frame(
          interval = label,
          k = k,
          metric = metric,
          successful = sum(status$success),
          attempted = B,
          median = s[1],
          lower = s[2],
          upper = s[3]
        )
      )
    }
  }
  cv <- assignments <- data.frame()
  set.seed(seed + end + 1000)
  for (r in seq_len(repeats)) {
    folds <- sample(rep(seq_len(folds_n), length.out = nrow(y)))
    assignments <- rbind(
      assignments,
      data.frame(repeat_id = r, subject_id = rownames(y), fold = folds)
    )
    for (f in seq_len(folds_n)) {
      train <- grid_fpca(y[folds != f, , drop = FALSE], g)
      test <- y[folds == f, , drop = FALSE]
      for (k in 0:4) {
        cv <- rbind(
          cv,
          data.frame(
            repeat_id = r,
            subject_id = rownames(test),
            fold = f,
            k = k,
            weighted_rmse = reconstruction_errors(train, test, k)
          )
        )
      }
    }
  }
  write_table(assignments, paste0(label, '_folds_private.csv'))
  write_table(cv, paste0(label, '_reconstruction_private.csv'))
  for (k in 0:4) {
    z <- cv[cv$k == k, ]
    repeated <- aggregate(weighted_rmse ~ repeat_id, z, mean)
    all_cv <- rbind(
      all_cv,
      data.frame(
        interval = label,
        k = k,
        n_subjects = nrow(y),
        repeats = repeats,
        mean_subject_rmse = mean(z$weighted_rmse),
        median_subject_repeat_rmse = median(z$weighted_rmse),
        min_repeat_mean = min(repeated$weighted_rmse),
        max_repeat_mean = max(repeated$weighted_rmse)
      )
    )
  }
  metrics <- cbind(
    mean_VAS = rowMeans(y),
    trapezoidal_AUC = as.vector(y %*% fp$weights),
    first_observed_peak_minute = g[max.col(y, ties.method = 'first')]
  )
  for (k in 1:4) {
    for (metric in colnames(metrics)) {
      all_redundancy <- rbind(
        all_redundancy,
        data.frame(
          interval = label,
          k = k,
          metric = metric,
          spearman = if (sd(metrics[, metric]) == 0) {
            NA_real_
          } else {
            cor(fp$scores[, k], metrics[, metric], method = 'spearman')
          },
          n_subjects = nrow(y)
        )
      )
    }
  }
  all_summary <- rbind(
    all_summary,
    data.frame(
      interval = label,
      n_subjects = nrow(y),
      k = 1:4,
      eigenvalue = fp$values,
      fve = fp$fve,
      cumulative_fve = cumsum(fp$fve),
      sample_fve90_crossing = if (any(cumsum(fp$fve) >= .9)) {
        which(cumsum(fp$fve) >= .9)[1]
      } else {
        NA
      }
    )
  )
  cat(
    label,
    ':',
    nrow(y),
    'complete subjects;',
    sum(status$success),
    '/',
    B,
    'bootstrap; CV finished\n'
  )
  flush.console()
}
write_table(all_summary, 'eigenvalues.csv')
write_table(all_cv, 'reconstruction_summary.csv')
write_table(all_stability, 'stability_summary.csv')
write_table(all_redundancy, 'redundancy.csv')
png(file.path(out, 'fpca_followup.png'), width = 1600, height = 1100, res = 150)
par(mfrow = c(2, 2), mar = c(4, 4, 3, 1))
for (label in unique(all_summary$interval)) {
  z <- all_summary[all_summary$interval == label, ]
  plot(
    z$k,
    z$cumulative_fve,
    type = 'b',
    ylim = c(0, 1),
    xaxt = 'n',
    xlab = 'Components',
    ylab = 'Cumulative variance fraction',
    main = paste(label, 'n =', z$n_subjects[1])
  )
  axis(1, 1:4)
  abline(h = .9, lty = 2, col = 'gray')
  z <- all_stability[
    all_stability$interval == label & all_stability$metric == 'max_angle_deg',
  ]
  plot(
    z$k,
    z$median,
    type = 'b',
    ylim = c(0, 90),
    xaxt = 'n',
    xlab = 'Leading components',
    ylab = 'Maximum subspace angle (degrees)',
    main = 'Bootstrap median and 2.5-97.5 percentiles'
  )
  axis(1, 1:4)
  segments(z$k, z$lower, z$k, z$upper, col = '#2166ac', lwd = 2)
}
dev.off()
writeLines(capture.output(sessionInfo()), file.path(out, 'sessionInfo.txt'))
