args <- commandArgs(trailingOnly = TRUE)
source(file.path(args[1], "R/vas_models.R"))
source(file.path(args[1], "R/derivative_calibration.R"))
source(file.path(args[1], "R/derivative_candidate_v3.R"))
source(file.path(args[1], "R/derivative_bootstrap_v4.R"))
original <- list(estimate = c(1, 2), se = c(1, 1))
est <- rbind(c(2, 4), c(3, 5), c(4, 6))
ses <- matrix(1, 3, 2)
bands <- bootstrap_derivative_bands(original, est, ses, level = 1)
stopifnot(
  all(bands$subject_bootstrap_t$critical == 4),
  all(bands$subject_bootstrap_bias_corrected_t$critical == 1),
  all(bands$subject_bootstrap_bias_corrected_t$estimate == c(-1, -1))
)
bad <- tryCatch(
  {
    bootstrap_derivative_bands(original, est, ses * 0)
    FALSE
  },
  error = function(e) TRUE
)
stopifnot(bad)
set.seed(99174)
d <- synthetic_derivative_data("curved_dropout", 40)$data
before <- d
fast <- fit_bootstrap_curve(d)
reference <- fit_bs_v3(d, 8)
stopifnot(
  max(abs(fast$beta - reference$beta)) < 1e-8,
  max(abs(fast$cov - reference$model_cov)) < 1e-8,
  identical(d, before)
)
sampled <- resample_subjects(d)
stopifnot(length(unique(sampled$subject_id)) == 40)
for (z in split(sampled, sampled$subject_id)) {
  stopifnot(any(vapply(
    split(d, d$subject_id),
    function(src) {
      identical(z$time_min, src$time_min) && identical(z$vas, src$vas)
    },
    logical(1)
  )))
}
cat(
  "PASS: hand-computed max-t and bias correction, invalid SE rejection, refit equivalence, subject trajectory/missingness preservation\n"
)
