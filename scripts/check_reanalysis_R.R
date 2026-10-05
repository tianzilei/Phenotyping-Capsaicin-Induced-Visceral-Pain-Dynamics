cat(R.version.string, '\n')
print(.libPaths())
for (p in c('mgcv', 'nlme', 'fdapace', 'jsonlite', 'clubSandwich', 'mne')) {
  cat(
    p,
    if (requireNamespace(p, quietly = TRUE)) {
      as.character(packageVersion(p))
    } else {
      'MISSING'
    },
    '\n'
  )
}
