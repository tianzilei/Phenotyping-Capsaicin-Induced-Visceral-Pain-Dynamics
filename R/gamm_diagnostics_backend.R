# Diagnostic-only reference refits. No changes to fit_vas_gamm or exclusion policy.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3L, dir.exists(args[3L]), !file.exists(args[2L]))
.libPaths(c(normalizePath(args[3L]), .libPaths()))
expected <- read.csv('dependencies/r-runtime-20261003-v1.csv', stringsAsFactors = FALSE)
for (i in seq_len(nrow(expected))) {
  observed <- if (expected$package[i] == 'R') {
    getRversion()
  } else {
    packageVersion(expected$package[i])
  }
  stopifnot(observed == package_version(expected$version[i]))
}
source('R/vas_models.R')
suppressPackageStartupMessages(library(mgcv))
request <- jsonlite::fromJSON(args[1L], simplifyVector = FALSE)
vec <- function(x) unlist(x, use.names = FALSE)
RNGkind('Mersenne-Twister', 'Inversion', 'Rejection')
set.seed(as.integer(request$seed))
d <- data.frame(
  subject_id = as.character(vec(request$data$person)),
  time_min = as.numeric(vec(request$data$time)),
  vas = as.numeric(vec(request$data$vas))
)
stopifnot(
  !anyDuplicated(d[c('subject_id', 'time_min')]),
  all(is.finite(d$vas)),
  all(is.finite(d$time_min)),
  all(d$vas >= 0 & d$vas <= 10)
)
warnings_log <- character()
answer <- tryCatch(
  withCallingHandlers(
    {
      fit <- fit_vas_gamm(d, as.integer(request$k), isTRUE(request$correlated))
      a <- fit$lme$apVar
      finite <- is.matrix(a) && all(is.finite(a))
      vc <- nlme::VarCorr(fit$lme)
      spectrum <- if (finite) {
        eigen((a + t(a)) / 2, symmetric = TRUE, only.values = TRUE)$values
      } else {
        NULL
      }
      list(
        status = 'estimated',
        curve = as.vector(predict(fit$gam, data.frame(time_min = vec(request$grid)))),
        VarCorr_text = capture.output(print(vc)),
        VarCorr_rows = rownames(vc),
        VarCorr_columns = colnames(vc),
        VarCorr_values = matrix(as.character(vc), nrow = nrow(vc), ncol = ncol(vc)),
        residual_sigma = fit$lme$sigma,
        logLik = as.numeric(logLik(fit$lme)),
        edf = sum(fit$gam$edf),
        optimizer_iterations = fit$lme$numIter,
        optimizer_exit_code = NULL,
        optimizer_exit_code_note = 'Not retained in returned lme object; no fabricated code',
        rho = if (is.null(fit$lme$modelStruct$corStruct)) {
          NULL
        } else {
          as.numeric(coef(fit$lme$modelStruct$corStruct, unconstrained = FALSE))
        },
        rho_unconstrained = if (is.null(fit$lme$modelStruct$corStruct)) {
          NULL
        } else {
          as.numeric(coef(fit$lme$modelStruct$corStruct, unconstrained = TRUE))
        },
        apVar_class = class(a),
        apVar_finite_matrix = finite,
        apVar_message = if (is.character(a)) a else NULL,
        apVar_matrix = if (finite) unname(a) else NULL,
        apVar_parameter_names = if (finite) rownames(a) else NULL,
        apVar_Pars = if (finite) attr(a, 'Pars') else NULL,
        apVar_natural = if (finite) attr(a, 'natural') else NULL,
        apVar_covariance_eigenvalues = spectrum,
        apVar_positive_definite = if (finite) min(spectrum) > 0 else NULL,
        apVar_covariance_condition_number = if (finite && min(spectrum) > 0) {
          max(spectrum) / min(spectrum)
        } else {
          NULL
        },
        Hessian = NULL,
        Hessian_note = 'apVar is an approximate covariance, not the Hessian; no Hessian recomputation in this diagnostic phase',
        model_formula = paste(deparse(formula(fit$lme)), collapse = ' ')
      )
    },
    warning = function(w) {
      warnings_log <<- c(warnings_log, conditionMessage(w))
      invokeRestart('muffleWarning')
    }
  ),
  error = function(e) list(status = 'inestimable', reason = conditionMessage(e))
)
answer$task <- request$task
answer$warnings <- unique(warnings_log)
answer$R_version <- as.character(getRversion())
answer$session_info <- capture.output(sessionInfo())
jsonlite::write_json(
  answer,
  args[2L],
  auto_unbox = TRUE,
  pretty = TRUE,
  na = 'null',
  null = 'null',
  digits = 16
)
