# Deterministic approximation diagnostic, distinct from coverage simulations.
args <- commandArgs(trailingOnly = TRUE)
root <- args[1]
out <- args[2]
if (dir.exists(out)) {
  stop("Refuse to overwrite")
}
dir.create(out, recursive = TRUE)
source(file.path(root, "R/derivative_calibration.R"))
suppressPackageStartupMessages(library(mgcv))
t <- 1:20
h <- 1e-4
lo <- pmax(1, t - h)
hi <- pmin(20, t + h)
truth <- .5 - .04 * t
y <- 2 + .5 * t - .02 * t^2
result <- data.frame()
for (k in c(6, 10)) {
  sm <- smoothCon(
    s(time_min, bs = "cr", k = k),
    data = data.frame(time_min = t),
    absorb.cons = FALSE
  )[[1]]
  beta <- qr.solve(sm$X, y)
  dx <- (PredictMat(sm, data.frame(time_min = hi)) -
    PredictMat(sm, data.frame(time_min = lo))) /
    (hi - lo)
  estimate <- as.vector(dx %*% beta)
  result <- rbind(
    result,
    data.frame(
      method = paste0("unpenalized_cr", k),
      time_min = t,
      truth = truth,
      estimate = estimate,
      bias = estimate - truth
    )
  )
}
beta <- qr.solve(bs_design(t), y)
estimate <- as.vector(bs_derivative(t) %*% beta)
result <- rbind(
  result,
  data.frame(
    method = "unpenalized_bs6",
    time_min = t,
    truth = truth,
    estimate = estimate,
    bias = estimate - truth
  )
)
write.csv(result, file.path(out, "noiseless_basis_bias.csv"), row.names = FALSE)
writeLines(capture.output(sessionInfo()), file.path(out, "sessionInfo.txt"))
cat("Noiseless quadratic projection, endpoints:\n")
print(result[result$time_min %in% c(1, 20), ], row.names = FALSE)
