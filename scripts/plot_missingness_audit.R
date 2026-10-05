args <- commandArgs(trailingOnly = TRUE)
out <- args[1]
d <- read.csv(file.path(out, 'minute_missingness_counts.csv'))
png(file.path(out, 'missingness_audit.png'), width = 1600, height = 1100, res = 150)
par(mfrow = c(2, 2), mar = c(4, 4, 3, 1), oma = c(4, 0, 0, 0))
for (g in c('all', 'E', 'T', 'none')) {
  z <- d[d$group == g, ]
  tot = z$n_subjects
  mat <- t(rbind(
    z$observed,
    z$termination_E,
    z$termination_T,
    z$pre_marker_missing,
    z$post_termination_missing
  ))
  barplot(
    t(mat),
    beside = FALSE,
    col = c('#4b8e71', '#cc9a3d', '#a95145', '#777777', '#355e98'),
    names.arg = z$time_min,
    xlab = 'Minute',
    ylab = 'Subjects',
    main = paste('Status by minute:', g)
  )
}
par(oma = c(0, 0, 0, 0), fig = c(0, 1, 0, .06), new = TRUE, mar = c(0, 0, 0, 0))
plot.new()
legend(
  'center',
  legend = c('Observed', 'E-coded', 'T-coded', 'Pre-marker blank', 'Post-marker blank'),
  fill = c('#4b8e71', '#cc9a3d', '#a95145', '#777777', '#355e98'),
  horiz = TRUE,
  bty = 'n',
  cex = .85
)
dev.off()
writeLines(capture.output(sessionInfo()), file.path(out, 'sessionInfo.txt'))
