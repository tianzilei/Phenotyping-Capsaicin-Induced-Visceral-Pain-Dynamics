# Portable task backend. Whole-person draws and folds are explicit inputs.
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
source('R/fpca_followup.R')
source('R/sparse_fpca.R')
suppressPackageStartupMessages(library(mgcv))
request <- jsonlite::fromJSON(args[1L], simplifyVector = FALSE)
RNGkind('Mersenne-Twister', 'Inversion', 'Rejection')
set.seed(as.integer(request$seed))
vec <- function(x) unlist(x, use.names = FALSE)
matrix_rows <- function(x) do.call(rbind, lapply(x, vec))
if (grepl('_bootstrap$', request$kind)) {
  stopifnot(length(request$replicate_seeds) == length(request$draws))
}
with_draws <- function(fun) {
  lapply(seq_along(request$draws), function(i) {
    set.seed(as.integer(request$replicate_seeds[[i]]))
    fun(request$draws[[i]])
  })
}
person_constant_errors <- function(y, weights) {
  stopifnot(length(weights) == ncol(y), all(weights > 0), all(is.finite(y)))
  constant <- as.vector(y %*% weights) / sum(weights)
  residual <- y - constant
  sqrt(rowSums(sweep(residual^2, 2, weights, '*')) / sum(weights))
}
warnings_log <- character()
capture <- function(code) {
  tryCatch(
    withCallingHandlers(code, warning = function(w) {
      warnings_log <<- c(warnings_log, conditionMessage(w))
      invokeRestart('muffleWarning')
    }),
    error = function(e) list(status = 'inestimable', reason = conditionMessage(e))
  )
}
diagnostics <- function(fit, grid) {
  d <- nlme::getData(fit$lme)
  r <- as.vector(residuals(fit$lme, type = 'normalized'))
  adjacent <- do.call(
    rbind,
    lapply(split(data.frame(d, r = r), d$subject_id), function(z) {
      z <- z[order(z$time_min), ]
      ix <- which(diff(z$time_min) == 1)
      data.frame(a = z$r[ix], b = z$r[ix + 1])
    })
  )
  curve <- as.vector(predict(fit$gam, data.frame(time_min = grid)))
  rho <- if (is.null(fit$lme$modelStruct$corStruct)) {
    NULL
  } else {
    as.numeric(coef(fit$lme$modelStruct$corStruct, unconstrained = FALSE))
  }
  by_minute <- split(r, d$time_min)
  list(
    edf = sum(fit$gam$edf),
    rho = rho,
    correlation_boundary = if (is.null(rho)) NULL else (rho < 1e-6 || rho > 1 - 1e-6),
    apVar_ok = is.matrix(fit$lme$apVar) && all(is.finite(fit$lme$apVar)),
    apVar_detail = if (is.character(fit$lme$apVar)) fit$lme$apVar else '',
    optimizer_iterations = fit$lme$numIter,
    residual_time = list(
      minute = as.numeric(names(by_minute)),
      n = vapply(by_minute, length, integer(1)),
      variance = vapply(by_minute, var, numeric(1))
    ),
    residual_adjacent_pairs = nrow(adjacent),
    residual_adjacent_correlation = if (nrow(adjacent) > 1) {
      cor(adjacent$a, adjacent$b)
    } else {
      NA_real_
    },
    residual_quantiles = as.numeric(quantile(r, c(0, .025, .25, .5, .75, .975, 1))),
    fitted_out_of_0_10 = sum(curve < 0 | curve > 10),
    n_observations = nrow(d),
    n_people = length(unique(d$subject_id))
  )
}
task <- request$task
if (request$kind == 'qa') {
  # Execute the repository's existing synthetic estimator checks unchanged.
  old_args <- commandArgs
  commandArgs <- function(trailingOnly = FALSE) {
    if (trailingOnly) getwd() else old_args(FALSE)
  }
  qa_env <- new.env(parent = globalenv())
  source('scripts/test_vas_models.R', local = qa_env)
  rm(commandArgs)
  source('scripts/test_sparse_fpca.R', local = qa_env)
  source('scripts/test_distributed_R_backend.R', local = qa_env)
  answer <- list(
    status = 'PASS',
    checks = c(
      'legacy_GAMM_actual_gaps_subject_resample',
      'legacy_weighted_FPCA_alignment_zero_variance',
      'legacy_sparse_fdapace',
      'training_only_reconstruction_person_constant_baseline'
    )
  )
} else if (request$kind %in% c('gamm_reference', 'gamm_bootstrap')) {
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
  grid <- as.numeric(vec(request$grid))
  answer <- capture({
    if (request$kind == 'gamm_reference') {
      fit <- fit_vas_gamm(d, as.integer(request$k), isTRUE(request$correlated))
      list(
        status = 'estimated',
        curve = as.vector(predict(fit$gam, data.frame(time_min = grid))),
        diagnostics = diagnostics(fit, grid),
        empirical_mean = as.vector(tapply(d$vas, d$time_min, mean))
      )
    } else {
      ids <- sort(unique(d$subject_id))
      rows <- with_draws(function(draw) {
        ix <- as.integer(vec(draw))
        stopifnot(length(ix) == length(ids), all(ix >= 0 & ix < length(ids)))
        capture({
          b <- do.call(
            rbind,
            lapply(seq_along(ix), function(j) {
              z <- d[d$subject_id == ids[ix[j] + 1L], ]
              z$subject_id <- paste0('copy_', j)
              z
            })
          )
          fit <- fit_vas_gamm(b, as.integer(request$k), isTRUE(request$correlated))
          list(
            status = 'estimated',
            curve = as.vector(predict(fit$gam, data.frame(time_min = grid))),
            diagnostics = diagnostics(fit, grid)
          )
        })
      })
      list(status = 'batch_completed', replicates = rows)
    }
  })
} else if (
  request$kind %in%
    c('complete_reference', 'complete_bootstrap', 'complete_reconstruction')
) {
  y <- matrix_rows(request$data$y)
  grid <- as.numeric(vec(request$grid))
  stopifnot(
    ncol(y) == length(grid),
    all(is.finite(y)),
    all(y >= 0 & y <= 10),
    nrow(y) >= 5
  )
  answer <- capture({
    if (request$kind == 'complete_reference') {
      fit <- grid_fpca(y, grid)
      list(
        status = 'estimated',
        eigenvalue = fit$values,
        fve = fit$fve,
        phi = fit$phi,
        mean = fit$mean
      )
    } else if (request$kind == 'complete_bootstrap') {
      reference <- grid_fpca(y, grid)
      list(
        status = 'batch_completed',
        replicates = with_draws(function(draw) {
          capture({
            ix <- as.integer(vec(draw))
            stopifnot(length(ix) == nrow(y), all(ix >= 0 & ix < nrow(y)))
            fit <- grid_fpca(y[ix + 1L, , drop = FALSE], grid)
            matched <- axis_match(reference, fit)
            list(
              status = 'estimated',
              cumulative_fve = cumsum(fit$fve),
              angle_deg = sapply(1:4, function(k) {
                principal_angle(reference$phi, fit$phi, reference$weights, k)
              }),
              matched_inner = matched$correlation,
              matched_component = matched$permutation
            )
          })
        })
      )
    } else {
      tr <- as.integer(vec(request$train))
      te <- as.integer(vec(request$test))
      stopifnot(
        !length(intersect(tr, te)),
        identical(sort(c(tr, te)), seq_len(nrow(y)) - 1L)
      )
      fit <- grid_fpca(y[tr + 1L, , drop = FALSE], grid)
      test <- y[te + 1L, , drop = FALSE]
      baseline <- person_constant_errors(test, fit$weights)
      errors <- sapply(0:4, function(k) reconstruction_errors(fit, test, k))
      list(
        status = 'estimated',
        test_rows = te,
        train_rows = tr,
        person_constant_rmse = baseline,
        rmse_k0_to_4 = errors,
        paired_loss_difference = sweep(errors, 1, baseline, '-'),
        training_mean = fit$mean
      )
    }
  })
} else if (request$kind %in% c('sparse_reference', 'sparse_bootstrap')) {
  input <- list(
    Ly = lapply(request$data$Ly, function(z) as.numeric(vec(z))),
    Lt = lapply(request$data$Lt, function(z) as.numeric(vec(z)))
  )
  stopifnot(
    length(input$Ly) == length(input$Lt),
    all(lengths(input$Ly) == lengths(input$Lt)),
    all(vapply(input$Lt, function(t) !anyDuplicated(t) && !is.unsorted(t), logical(1)))
  )
  op <- request$options
  answer <- capture({
    reference <- sparse_fit(input, op)
    check_sparse_fit(reference, length(input$Ly))
    if (request$kind == 'sparse_reference') {
      list(
        status = 'estimated',
        mean = reference$mu,
        grid = reference$workGrid,
        phi = reference$phi,
        eigenvalue = reference$lambda,
        cumulative_fve = sparse_fve(reference),
        sigma2 = reference$sigma2,
        actual_options = reference$optns
      )
    } else {
      list(
        status = 'batch_completed',
        replicates = with_draws(function(draw) {
          capture({
            ix <- as.integer(vec(draw))
            stopifnot(
              length(ix) == length(input$Ly),
              all(ix >= 0 & ix < length(input$Ly))
            )
            fit <- sparse_fit(list(Ly = input$Ly[ix + 1L], Lt = input$Lt[ix + 1L]), op)
            check_sparse_fit(fit, length(ix))
            list(
              status = 'estimated',
              angle_deg = sapply(1:4, function(k) sparse_angle(reference, fit, k)),
              cumulative_fve = sparse_fve(fit),
              sigma2 = fit$sigma2
            )
          })
        })
      )
    }
  })
} else {
  stop('Unsupported R task kind')
}
answer$task <- task
answer$warnings <- unique(warnings_log)
answer$R_version <- as.character(getRversion())
answer$library_paths <- .libPaths()
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
