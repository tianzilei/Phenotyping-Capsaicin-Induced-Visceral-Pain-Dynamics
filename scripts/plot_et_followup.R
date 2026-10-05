args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
d <- read.csv(file.path(out, "marker_distribution.csv"))
b <- read.csv(file.path(out, "cohort_mean_identification_bounds.csv"))
o <- read.csv(file.path(out, "observed_curve_subject_bootstrap.csv"))
g <- read.csv(file.path(out, "observed_by_eventual_marker.csv"))
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
png(
  file.path(out, "stopping_and_missingness.png"),
  width = 1600,
  height = 1200,
  res = 160
)
par(mfrow = c(2, 2), mar = c(4.2, 4.2, 3, 1))
matplot(
  d$time_min,
  cbind(d$fraction_E_by_minute, d$fraction_T_by_minute),
  type = "s",
  lty = 1,
  lwd = 2,
  col = c("#227746", "#af3a36"),
  ylim = c(0, 1),
  xlab = "First marker column (minute)",
  ylab = "Fraction of all candidate rows",
  main = "Recorded stopping markers (not event times)"
)
legend(
  "topleft",
  c("E: stopped after no pain for 2 min", "T: discontinued"),
  col = c("#227746", "#af3a36"),
  lty = 1,
  bty = "n",
  cex = .75
)
plot(
  o$time_min,
  o$mean_observed,
  type = "n",
  ylim = c(0, 10),
  xlab = "Minute",
  ylab = "VAS (0-10)",
  main = "Mean among observed rows; 95% pointwise CI"
)
polygon(
  c(o$time_min, rev(o$time_min)),
  c(o$bootstrap_pointwise_lower, rev(o$bootstrap_pointwise_upper)),
  col = "#d3e2f0",
  border = NA
)
lines(o$time_min, o$mean_observed, col = "#245b85", lwd = 2)
plot(
  b$time_min,
  b$cohort_mean_lower,
  type = "n",
  ylim = c(0, 10),
  xlab = "Minute",
  ylab = "Cohort mean VAS",
  main = "Bounds from unobserved VAS in [0, 10]"
)
polygon(
  c(b$time_min, rev(b$time_min)),
  c(b$cohort_mean_lower, rev(b$cohort_mean_upper)),
  col = "#e8dfcc",
  border = NA
)
lines(b$time_min, b$cohort_mean_lower, col = "#8f6c2b")
lines(b$time_min, b$cohort_mean_upper, col = "#8f6c2b")
lines(o$time_min, o$mean_observed, col = "#245b85", lwd = 2)
legend(
  "topleft",
  c("Identification range (not a CI)", "Observed-row mean (different estimand)"),
  fill = c("#e8dfcc", NA),
  border = c(NA, NA),
  lty = c(NA, 1),
  col = c(NA, "#245b85"),
  bty = "n",
  cex = .72
)
matplot(
  b$time_min,
  cbind(b$width_due_to_E, b$width_due_to_T, b$width_due_to_other_missing),
  type = "l",
  lty = 1,
  lwd = 2,
  col = c("#227746", "#af3a36", "#666666"),
  xlab = "Minute",
  ylab = "Contribution to mean-bound width",
  main = "Uncertainty from E, T and other missingness"
)
legend(
  "topleft",
  c("After/at E", "After/at T", "Other missing"),
  col = c("#227746", "#af3a36", "#666666"),
  lty = 1,
  bty = "n",
  cex = .8
)
dev.off()
png(file.path(out, "observed_by_marker.png"), width = 1400, height = 900, res = 150)
par(mfrow = c(2, 1), mar = c(4, 4, 2, 1))
colors <- c(E = "#227746", T = "#af3a36", none = "#245b85")
plot(
  1:20,
  rep(NA, 20),
  ylim = c(0, 10),
  xlab = "Minute",
  ylab = "Observed VAS mean",
  main = "Descriptive groups defined by eventual marker"
)
for (code in names(colors)) {
  z <- g[g$eventual_marker == code, ]
  lines(z$time_min, z$mean_observed, col = colors[code], lwd = 2)
}
legend("topright", names(colors), col = colors, lty = 1, bty = "n")
plot(
  1:20,
  rep(NA, 20),
  ylim = c(0, max(g$n_observed)),
  xlab = "Minute",
  ylab = "Number observed",
  main = "Available observations in each eventual-marker group"
)
for (code in names(colors)) {
  z <- g[g$eventual_marker == code, ]
  lines(z$time_min, z$n_observed, col = colors[code], lwd = 2)
}
dev.off()
