cat(R.version.string, "\n")
for (p in c("mgcv", "nlme", "fdapace", "jsonlite")) {
  cat(
    p,
    if (requireNamespace(p, quietly = TRUE)) {
      as.character(packageVersion(p))
    } else {
      "MISSING"
    },
    "\n"
  )
}
