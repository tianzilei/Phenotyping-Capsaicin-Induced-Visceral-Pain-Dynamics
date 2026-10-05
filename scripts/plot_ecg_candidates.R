args <- commandArgs(trailingOnly = TRUE)
run <- args[1]
out <- args[2]
d <- read.csv(file.path(run, 'windows_private.csv'))
b <- read.csv(file.path(run, 'between_channels_private.csv'))
s <- read.csv(file.path(run, 'synthetic_summary.csv'))
draw <- function() {
  par(mfrow = c(2, 2), mar = c(4, 4, 3, 1))
  hist(
    d$agreement,
    breaks = seq(0, 1, by = .05),
    col = '#3A6D8C',
    xlim = c(0, 1),
    main = 'Two-method agreement',
    xlab = '2 matched / total candidates',
    ylab = 'Channel windows'
  )
  boxplot(
    agreement ~ method,
    data = b,
    ylim = c(0, 1),
    col = c('#3A6D8C', '#C38138'),
    main = 'Between-channel agreement',
    ylab = '2 matched / total candidates'
  )
  plot(
    d$amplitude_candidate_count,
    d$energy_candidate_count,
    pch = 16,
    cex = .45,
    col = rgb(.2, .4, .6, .3),
    xlab = 'Amplitude candidates / 280 s',
    ylab = 'Energy candidates / 280 s',
    main = 'All windows, no lead selection'
  )
  abline(0, 1, lty = 2)
  noise <- subset(s, case == 'noise_only')
  barplot(
    noise$candidate_count / noise$replicates,
    names.arg = noise$method,
    col = c('#3A6D8C', '#C38138'),
    main = 'Noise-only synthetic controls',
    ylab = 'False candidates / 100 s'
  )
}
png(file.path(out, 'candidate_diagnostics.png'), width = 1500, height = 1050, res = 130)
draw()
dev.off()
pdf(file.path(out, 'candidate_diagnostics.pdf'), width = 11.5, height = 8)
draw()
dev.off()
tr <- read.csv(file.path(out, 'review_traces_private.csv'))
marks <- read.csv(file.path(out, 'review_markers_private.csv'))
draw_traces <- function() {
  examples <- unique(tr$example)
  par(mfrow = c(length(examples), 1), mar = c(3, 4, 2, 1))
  for (ex in examples) {
    a <- subset(tr, example == ex)
    m <- subset(marks, example == ex)
    plot(
      a$time_s,
      a$filtered_mV,
      type = 'l',
      xlab = 'Seconds from recording start',
      ylab = 'Filtered mV',
      main = ex
    )
    for (method in c('amplitude', 'energy')) {
      q <- subset(m, detector == method)
      points(
        q$time_s,
        approx(a$time_s, a$filtered_mV, xout = q$time_s)$y,
        pch = if (method == 'amplitude') 1 else 3,
        col = if (method == 'amplitude') '#BE5729' else '#00788C'
      )
    }
    legend(
      'topright',
      legend = c('amplitude candidate', 'energy candidate'),
      pch = c(1, 3),
      col = c('#BE5729', '#00788C'),
      bty = 'n',
      cex = .8
    )
  }
}
png(file.path(out, 'review_traces_private.png'), width = 1500, height = 1100, res = 130)
draw_traces()
dev.off()
