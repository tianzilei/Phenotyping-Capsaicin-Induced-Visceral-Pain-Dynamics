# Planned statistical APIs. These are not implemented estimators.
not_implemented <- function(module) {
  stop(
    paste(
      module,
      "is an interface only; implement and validate per docs/analysis_plan.md"
    ),
    call. = FALSE
  )
}
fit_gamm <- function(vas_long, config) not_implemented("M02 GAMM")
estimate_derivatives <- function(gamm_result, config) not_implemented("M02 derivatives")
fit_fpca <- function(vas_long, config) not_implemented("M03 FPCA")
fit_variability <- function(vas_long, subject_trends, config) {
  not_implemented("M04 variability")
}
fit_physiology <- function(vas_long, physiology_windows, config) {
  not_implemented("M06 physiology")
}
fit_markov <- function(vas_long, termination_events, physiology_windows, config) {
  not_implemented("M07 Markov")
}
