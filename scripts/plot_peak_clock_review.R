args <- commandArgs(trailingOnly = TRUE)
egg <- args[1]
out <- args[2]
v <- read.csv(file.path(egg, 'variant_summary.csv'))
s <- read.csv(file.path(egg, 'synthetic_summary.csv'))
draw <- function() {
  par(mfrow = c(1, 2), mar = c(10, 4, 3, 1))
  b <- barplot(
    100 * v$boundary_maxima / v$channel_windows,
    names.arg = c('Linear 128 s', 'Linear 256 s', 'Quadratic + 128 s'),
    las = 2,
    ylim = c(0, 100),
    col = c('#3A6D8C', '#C38138', '#639480'),
    ylab = 'Windows with boundary maximum (%)',
    main = 'Observed EGG: 1536 channel windows'
  )
  text(b, 100 * v$boundary_maxima / v$channel_windows + 4, labels = v$boundary_maxima)
  cases <- unique(s$case)
  m <- sapply(v$variant, function(x) {
    s$boundary_maxima[match(paste(cases, x), paste(s$case, s$variant))] / 20 * 100
  })
  barplot(
    t(m),
    beside = TRUE,
    names.arg = gsub('_', ' ', cases),
    las = 2,
    ylim = c(0, 120),
    col = c('#3A6D8C', '#C38138', '#639480'),
    ylab = 'Replicates with boundary maximum (%)',
    main = 'Synthetic controls: 20 per case'
  )
  legend(
    'topright',
    legend = c('Linear 128 s', 'Linear 256 s', 'Quadratic + 128 s'),
    fill = c('#3A6D8C', '#C38138', '#639480'),
    cex = .75,
    bty = 'n'
  )
}
png(file.path(out, 'peak_sensitivity.png'), width = 1600, height = 850, res = 140)
draw()
dev.off()
pdf(file.path(out, 'peak_sensitivity.pdf'), width = 11.4, height = 6.1)
draw()
dev.off()
