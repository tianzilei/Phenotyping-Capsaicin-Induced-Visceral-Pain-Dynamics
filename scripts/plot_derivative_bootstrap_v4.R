args <- commandArgs(trailingOnly = TRUE)
run <- args[1]
out <- args[2]
s <- read.csv(file.path(run, "summary.csv"))
b <- read.csv(file.path(out, "bias_and_width.csv"))
methods <- c(
  "model_coefficient",
  "subject_bootstrap_t",
  "subject_bootstrap_bias_corrected_t"
)
colors <- c("#aa5947", "#428574", "#385ca3")
cells <- unique(s[, c("scenario", "n")])
png(file.path(out, "coverage.png"), width = 1700, height = 1000, res = 150)
par(mfrow = c(2, 3), mar = c(5, 4, 3, 1))
for (i in 1:nrow(cells)) {
  z <- s[s$scenario == cells$scenario[i] & s$n == cells$n[i], ]
  z <- z[match(methods, z$method), ]
  plot(
    1:3,
    z$coverage,
    ylim = c(0, 1),
    xlim = c(.5, 3.5),
    xaxt = "n",
    xlab = "",
    ylab = "Simultaneous coverage",
    main = paste(cells$scenario[i], "n =", cells$n[i]),
    pch = 16,
    col = colors
  )
  arrows(
    1:3,
    z$wilson_lower,
    1:3,
    z$wilson_upper,
    angle = 90,
    code = 3,
    length = .05,
    col = colors
  )
  axis(1, at = 1:3, labels = c("Model", "Boot-t", "Bias-corrected"), cex.axis = .8)
  abline(h = .95, lty = 2)
}
dev.off()
png(file.path(out, "bias.png"), width = 1700, height = 1000, res = 150)
par(mfrow = c(2, 3), mar = c(4, 4, 3, 1))
for (i in 1:nrow(cells)) {
  z <- b[b$scenario == cells$scenario[i] & b$n == cells$n[i], ]
  lim <- range(c(0, z$mean_bias))
  if (diff(lim) < .01) {
    lim <- lim + c(-.005, .005)
  }
  plot(
    1:20,
    rep(0, 20),
    type = "n",
    ylim = lim,
    xlab = "Minute",
    ylab = "Mean derivative bias",
    main = paste(cells$scenario[i], "n =", cells$n[i])
  )
  abline(h = 0, lty = 2)
  for (m in 1:3) {
    zz <- z[z$method == methods[m], ]
    lines(zz$time_min, zz$mean_bias, col = colors[m], lwd = 2, lty = m)
  }
  if (i == 1) {
    legend(
      "topleft",
      c("Model", "Boot-t", "Bias-corrected"),
      col = colors,
      lty = 1:3,
      cex = .7,
      bty = "n"
    )
  }
}
dev.off()
