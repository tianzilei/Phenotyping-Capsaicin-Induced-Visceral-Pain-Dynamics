args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
.libPaths(c('renv/library/sparse-fpca', .libPaths()))
config_path <- if (length(args) >= 2) args[2] else 'config/remaining_analysis_v1.json'
cfg <- jsonlite::fromJSON(config_path)
source('R/remaining_descriptives.R')
source('R/vas_models.R')
d <- read.csv(file.path(cfg$input_run, 'vas_long.csv'), stringsAsFactors = FALSE)
write_table <- function(x, n) {
  write.csv(x, file.path(out, n), row.names = FALSE, na = '')
}
res <- burden <- depths <- envelopes <- correlations <- data.frame()
for (end in c(20, 10)) {
  obs <- d[d$status == 'observed' & d$time_min <= end, ]
  groups <- split(obs, as.character(obs$subject_id), drop = TRUE)
  for (id in names(groups)) {
    z <- groups[[id]]
    pairs <- sum(diff(sort(z$time_min)) == 1)
    if (
      nrow(z) < cfg$residual$minimum_points ||
        pairs < cfg$residual$minimum_adjacent_pairs
    ) {
      next
    }
    for (degree in c(1, 2)) {
      m <- residual_metrics(z$time_min, z$vas, degree)
      res <- rbind(
        res,
        data.frame(
          subject_id = id,
          end_min = end,
          degree = degree,
          n = m['n'],
          pairs = m['pairs'],
          residual_variance = m['residual_variance'],
          residual_mssd = m['residual_mssd'],
          raw_mssd = m['raw_mssd'],
          complete = nrow(z) == end
        )
      )
    }
  }
  y <- complete_matrix(obs, 1:end)
  b <- t(apply(y, 1, function(v) burden_metrics(1:end, v)))
  burden <- rbind(burden, data.frame(subject_id = rownames(y), end_min = end, b))
  depth <- modified_band_depth(y, 1:end)
  depths <- rbind(
    depths,
    data.frame(
      subject_id = rownames(y),
      end_min = end,
      depth = depth$depth,
      central = depth$central
    )
  )
  envelopes <- rbind(
    envelopes,
    data.frame(
      end_min = end,
      time_min = 1:end,
      lower = depth$lower,
      upper = depth$upper,
      deepest = y[depth$deepest, ],
      n_complete = nrow(y),
      n_central = sum(depth$central)
    )
  )
  for (metric in c('time_centroid', 'late_area_fraction')) {
    for (reference in c('auc', 'first_observed_peak_minute')) {
      good <- is.finite(b[, metric]) & is.finite(b[, reference])
      correlations <- rbind(
        correlations,
        data.frame(
          end_min = end,
          metric = metric,
          reference = reference,
          n = sum(good),
          spearman = cor(b[good, metric], b[good, reference], method = 'spearman')
        )
      )
    }
  }
}
write_table(res, 'residual_metrics_private.csv')
write_table(burden, 'burden_metrics_private.csv')
write_table(depths, 'functional_depth_private.csv')
write_table(envelopes, 'functional_envelopes.csv')
write_table(correlations, 'burden_redundancy.csv')
summary <- data.frame()
set.seed(cfg$bootstrap$seed)
for (end in c(20, 10)) {
  for (degree in c(1, 2)) {
    z <- res[res$end_min == end & res$degree == degree, ]
    for (metric in c('residual_variance', 'residual_mssd', 'raw_mssd')) {
      v <- z[[metric]]
      boot <- replicate(
        cfg$bootstrap$replicates,
        median(sample(v, length(v), replace = TRUE))
      )
      summary <- rbind(
        summary,
        data.frame(
          module = 'residual',
          end_min = end,
          degree = degree,
          metric = metric,
          n = length(v),
          median = median(v),
          lower = quantile(boot, .025),
          upper = quantile(boot, .975)
        )
      )
    }
  }
  z <- burden[burden$end_min == end, ]
  for (metric in c('auc', 'time_centroid', 'late_area_fraction')) {
    v <- z[[metric]]
    v <- v[is.finite(v)]
    boot <- replicate(
      cfg$bootstrap$replicates,
      median(sample(v, length(v), replace = TRUE))
    )
    summary <- rbind(
      summary,
      data.frame(
        module = 'burden',
        end_min = end,
        degree = NA,
        metric = metric,
        n = length(v),
        median = median(v),
        lower = quantile(boot, .025),
        upper = quantile(boot, .975)
      )
    )
  }
}
write_table(summary, 'summary.csv')
png(file.path(out, 'functional_depth.png'), width = 1400, height = 700, res = 150)
par(mfrow = c(1, 2), mar = c(4, 4, 3, 1))
for (end in c(20, 10)) {
  z <- envelopes[envelopes$end_min == end, ]
  plot(
    z$time_min,
    z$deepest,
    type = 'n',
    ylim = range(c(z$lower, z$upper)),
    xlab = 'Actual minute',
    ylab = 'VAS',
    main = paste('Complete 1-', end, ':', z$n_complete[1], 'curves')
  )
  polygon(
    c(z$time_min, rev(z$time_min)),
    c(z$lower, rev(z$upper)),
    col = '#c9dce8',
    border = NA
  )
  lines(z$time_min, z$deepest, lwd = 2)
  legend(
    'topright',
    legend = c('Deepest curve', paste('Central set n =', z$n_central[1])),
    lty = c(1, NA),
    pch = c(NA, 15),
    col = c('black', '#c9dce8'),
    bty = 'n',
    cex = .7
  )
}
dev.off()
writeLines(capture.output(sessionInfo()), file.path(out, 'sessionInfo.txt'))
