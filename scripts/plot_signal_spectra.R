args <- commandArgs(trailingOnly = TRUE)
run <- args[1]
out <- args[2]
z <- read.csv(file.path(run, 'recording_summaries_private.csv'))
s <- read.csv(file.path(run, 'support_private.csv'))
e <- z[z$label == 'EGG100C', ]
png(
  file.path(out, 'signal_spectra_overview.png'),
  width = 1600,
  height = 1100,
  res = 150
)
par(mfrow = c(2, 2), mar = c(4.4, 4.4, 3.2, 1), oma = c(2.4, 0, 0, 0))
u <- s[!duplicated(s$path), ]
barplot(
  table(u$complete_windows),
  col = '#467f99',
  xlab = 'Complete 300-second windows per recording',
  ylab = 'Recordings',
  main = 'Recording support (no dose alignment)'
)
hist(
  e$median_norm_fraction,
  breaks = 20,
  col = '#628f74',
  border = 'white',
  xlab = 'Median narrow / broad band power',
  main = 'EGG: descriptive spectral fraction'
)
hist(
  e$median_band_max_cpm,
  breaks = 20,
  col = '#b49161',
  border = 'white',
  xlab = 'Within-band spectral maximum (cycles/min)',
  main = 'EGG: maximum is not a validated gastric peak'
)
hist(
  e$median_abs_peak_difference_cpm,
  breaks = 20,
  col = '#947fa4',
  border = 'white',
  xlab = 'Median absolute 128s vs 64s peak difference (cpm)',
  main = 'EGG: sensitivity to segment length'
)
mtext(
  'Each histogram entry is one recording summary; not independent subjects. Artifact acceptance is pending.',
  outer = TRUE,
  side = 1,
  line = .7,
  cex = .8
)
dev.off()
writeLines(capture.output(sessionInfo()), file.path(out, 'R_sessionInfo.txt'))
