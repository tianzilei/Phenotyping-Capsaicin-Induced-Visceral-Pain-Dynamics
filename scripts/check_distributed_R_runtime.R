# Read-only check: no package installation, profile activation, or analysis.
# Rscript --vanilla check_distributed_R_runtime.R expected.csv new-report.csv [library]
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2L || length(args) > 3L) {
  stop("Usage: expected.csv new-report.csv [explicit-library-path]")
}
if (file.exists(args[2L])) {
  stop("Report already exists; choose a new filename")
}
if (length(args) == 3L) {
  if (!dir.exists(args[3L])) {
    stop("Explicit library does not exist")
  }
  .libPaths(c(normalizePath(args[3L]), .libPaths()))
}
expected <- read.csv(args[1L], stringsAsFactors = FALSE)
if (
  !identical(names(expected), c("package", "version", "load_check")) ||
    anyDuplicated(expected$package) ||
    !all(expected$load_check %in% c(0L, 1L))
) {
  stop("Invalid expected-version table")
}
rows <- lapply(seq_len(nrow(expected)), function(i) {
  pkg <- expected$package[i]
  observed <- if (pkg == "R") {
    as.character(getRversion())
  } else {
    tryCatch(as.character(packageVersion(pkg)), error = function(e) NA_character_)
  }
  matched <- !is.na(observed) &&
    package_version(observed) == package_version(expected$version[i])
  load_result <- "not_requested"
  detail <- ""
  if (matched && pkg != "R" && expected$load_check[i] == 1L) {
    load_result <- tryCatch(
      {
        loadNamespace(pkg)
        "PASS"
      },
      error = function(e) {
        detail <<- conditionMessage(e)
        "LOAD_FAILED"
      }
    )
  }
  status <- if (is.na(observed)) {
    "MISSING"
  } else if (!matched) {
    "VERSION_MISMATCH"
  } else if (load_result == "LOAD_FAILED") {
    "LOAD_FAILED"
  } else {
    "PASS"
  }
  data.frame(
    package = pkg,
    expected = expected$version[i],
    observed = observed,
    status = status,
    load_check = load_result,
    detail = detail,
    libraries = paste(.libPaths(), collapse = ";"),
    stringsAsFactors = FALSE
  )
})
report <- do.call(rbind, rows)
# Exclusive-create to preserve previous reports, including concurrent checks.
handle <- file(args[2L], open = "wx")
tryCatch(write.csv(report, handle, row.names = FALSE, na = ""), finally = close(handle))
print(table(report$status))
cat("R executable:", file.path(R.home("bin"), "Rscript"), "\n")
quit(save = "no", status = if (all(report$status == "PASS")) 0L else 2L)
