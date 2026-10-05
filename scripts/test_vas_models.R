# Meaningful synthetic estimator checks, not clinical calibration.
args <- commandArgs(trailingOnly = TRUE)
source(file.path(args[1], "R/vas_models.R"))
suppressPackageStartupMessages(library(mgcv))
set.seed(84620)
d <- expand.grid(time_min = 1:20, subject_id = paste0("synthetic_", 1:40))
offset <- rnorm(40, 0, .5)
d$vas <- 2 + .15 * d$time_min + rep(offset, each = 20) + rnorm(nrow(d), 0, .12)
fit <- fit_vas_gamm(d, 6, FALSE)
mat <- prediction_matrices(fit, 1:20)
derivative <- as.vector(mat$dx %*% coef(fit$gam))
stopifnot(max(abs(derivative - .15)) < .04)
bands <- simultaneous_band(mat$dx, coef(fit$gam), fit$gam$Vp, 1000)
stopifnot(all(bands$lower > 0), all(bands$lower < bands$upper))
resampled <- resample_subjects(d)
stopifnot(
  length(unique(resampled$subject_id)) == 40,
  all(table(resampled$subject_id) == 20)
)
incomplete <- d[!(d$subject_id == "synthetic_1" & d$time_min == 5), ]
y <- complete_matrix(incomplete, 1:20)
stopifnot(nrow(y) == 39, !("synthetic_1" %in% rownames(y)))
g <- 1:20
level <- seq(-2, 2, length.out = 40)
shape <- sin(seq(0, 2 * pi, length.out = 40))
known <- outer(level, rep(1, 20)) + outer(shape, (g - 10.5) / 10) + 5
fp <- grid_fpca(known, g)
stopifnot(max(abs(crossprod(fp$phi, fp$weights * fp$phi) - diag(4))) < 1e-10)
reconstructed <- sweep(fp$scores[, 1:2] %*% t(fp$phi[, 1:2]), 2, fp$mean, "+")
stopifnot(max(abs(reconstructed - known)) < 1e-9, sum(fp$fve[1:2]) > .99999)
flipped <- fp
flipped$phi <- -fp$phi[, c(2, 1, 4, 3)]
matched <- axis_match(fp, flipped)
stopifnot(all(matched$correlation > .99999))
constant_error <- tryCatch(
  {
    grid_fpca(matrix(5, 40, 20), g)
    FALSE
  },
  error = function(e) TRUE
)
stopifnot(constant_error)
# CAR1 must use the actual time gaps and preserve the omitted observation.
gapfit <- fit_vas_gamm(incomplete, 6, TRUE)
stopifnot(nrow(nlme::getData(gapfit$lme)) == nrow(incomplete))
cat(
  "PASS: synthetic slope/bands, subject bootstrap, missing-time CAR1, complete-case selection, weighted FPCA/reconstruction, axis alignment, zero-variance rejection\n"
)
