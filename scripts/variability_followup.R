args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
B <- as.integer(args[2])
seed <- as.integer(args[3])
set.seed(seed)
d <- read.csv(
  file.path(out, "window_metrics_private.csv"),
  na.strings = "",
  stringsAsFactors = FALSE
)
d$eligible <- tolower(d$eligible) == "true"
d$complete <- tolower(d$complete) == "true"
metrics <- c(
  "mean_vas",
  "sample_sd",
  "mssd",
  "rmssd",
  "mean_adjacent_change",
  "centered_change_ms"
)
summary <- data.frame()
correlations <- data.frame()
counts <- data.frame()
interval <- function(x, fun = median) {
  if (length(x) < 2) {
    return(c(NA_real_, NA_real_))
  }
  quantile(
    replicate(B, fun(sample(x, length(x), replace = TRUE))),
    c(.025, .975),
    names = FALSE
  )
}
for (window in unique(d$window)) {
  for (policy in c("at_least_3_pairs", "complete_window")) {
    z <- d[
      d$window == window & if (policy == "at_least_3_pairs") d$eligible else d$complete,
    ]
    counts <- rbind(
      counts,
      data.frame(
        window = window,
        policy = policy,
        n = nrow(z),
        E = sum(z$marker == "E"),
        T = sum(z$marker == "T"),
        none = sum(z$marker == "none")
      )
    )
    if (nrow(z) == 0) {
      next
    }
    for (metric in metrics) {
      x <- z[[metric]]
      x <- x[is.finite(x)]
      ci <- interval(x)
      summary <- rbind(
        summary,
        data.frame(
          window = window,
          policy = policy,
          metric = metric,
          n = length(x),
          median = median(x),
          q25 = quantile(x, .25, names = FALSE),
          q75 = quantile(x, .75, names = FALSE),
          bootstrap_lower = ci[1],
          bootstrap_upper = ci[2]
        )
      )
    }
    for (other in c("mean_vas", "n_pairs")) {
      valid <- is.finite(z$mssd) & is.finite(z[[other]])
      x <- z$mssd[valid]
      y <- z[[other]][valid]
      r <- if (length(x) >= 3 && length(unique(x)) > 1 && length(unique(y)) > 1) {
        cor(x, y, method = "spearman")
      } else {
        NA_real_
      }
      correlations <- rbind(
        correlations,
        data.frame(
          window = window,
          policy = policy,
          x = "mssd",
          y = other,
          n = length(x),
          rho = r,
          reason = if (is.na(r)) {
            "undefined_constant_or_insufficient"
          } else {
            "descriptive_no_p_value"
          }
        )
      )
    }
  }
}
early <- d[d$window == "1_5" & d$complete, ]
late <- d[d$window == "16_20" & d$complete, ]
paired <- merge(early, late, by = "subject_id", suffixes = c("_early", "_late"))
paired_summary <- data.frame()
paired_values <- data.frame(subject_id = paired$subject_id)
for (metric in metrics) {
  delta <- paired[[paste0(metric, "_late")]] - paired[[paste0(metric, "_early")]]
  ci <- interval(delta, mean)
  paired_summary <- rbind(
    paired_summary,
    data.frame(
      metric = metric,
      n = length(delta),
      mean_late_minus_early = if (length(delta)) mean(delta) else NA_real_,
      bootstrap_lower = ci[1],
      bootstrap_upper = ci[2]
    )
  )
  paired_values[[paste0(metric, "_late_minus_early")]] <- delta
}
write.csv(summary, file.path(out, "window_summary.csv"), row.names = FALSE, na = "")
write.csv(counts, file.path(out, "eligibility_counts.csv"), row.names = FALSE, na = "")
write.csv(
  correlations,
  file.path(out, "descriptive_correlations.csv"),
  row.names = FALSE,
  na = ""
)
write.csv(
  paired_summary,
  file.path(out, "paired_early_late_summary.csv"),
  row.names = FALSE,
  na = ""
)
write.csv(
  paired_values,
  file.path(out, "paired_changes_private.csv"),
  row.names = FALSE,
  na = ""
)
png(file.path(out, "variability_windows.png"), width = 1500, height = 950, res = 150)
par(mfrow = c(2, 2), mar = c(4, 4, 3, 1))
for (metric in c("mean_vas", "sample_sd", "mssd", "mean_adjacent_change")) {
  z <- summary[
    summary$policy == "at_least_3_pairs" &
      summary$metric == metric &
      summary$window %in% c("1_5", "6_10", "11_15", "16_20"),
  ]
  z <- z[match(c("1_5", "6_10", "11_15", "16_20"), z$window), ]
  plot(
    1:4,
    z$median,
    ylim = range(z$bootstrap_lower, z$bootstrap_upper, z$median, na.rm = TRUE),
    type = "p",
    xaxt = "n",
    xlab = "Minute window",
    ylab = metric,
    main = "Observed subjects: median and pointwise CI",
    col = "#326b88",
    pch = 16
  )
  axis(
    1,
    1:4,
    labels = paste0(c("1-5", "6-10", "11-15", "16-20"), " (n=", z$n, ")"),
    cex.axis = .8
  )
  nonzero <- which(
    is.finite(z$bootstrap_lower) &
      is.finite(z$bootstrap_upper) &
      z$bootstrap_upper > z$bootstrap_lower
  )
  arrows(
    nonzero,
    z$bootstrap_lower[nonzero],
    nonzero,
    z$bootstrap_upper[nonzero],
    angle = 90,
    code = 3,
    length = .05,
    col = "#326b88"
  )
}
dev.off()
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
