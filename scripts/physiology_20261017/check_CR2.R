args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3, !file.exists(args[2]), !file.exists(args[3]))
suppressPackageStartupMessages(library(clubSandwich))
options(warn = 1)
d <- read.csv(args[1], stringsAsFactors = FALSE)
answer <- list()
for (id in unique(d$test_id)) {
  z <- d[d$test_id == id, ]
  z$person_id <- factor(z$person_id)
  z$block <- factor(z$block)
  hasHR <- all(tolower(as.character(z$has_HR)) == 'true')
  form <- if (hasHR) {
    value ~ vas_mean + HR + person_id + block
  } else {
    value ~ vas_mean + person_id + block
  }
  fit <- lm(form, data = z)
  v2 <- vcovCR(fit, cluster = z$person_id, type = 'CR2')
  result <- coef_test(fit, vcov = v2, test = 'Satterthwaite', coefs = 'vas_mean')
  df <- result$df_Satt
  b <- result$beta
  se <- result$SE
  v1 <- vcovCR(fit, cluster = z$person_id, type = 'CR1S')
  answer[[id]] <- data.frame(
    test_id = id,
    beta_R = b,
    se_CR1_R = sqrt(v1['vas_mean', 'vas_mean']),
    se_CR2_R = se,
    df_CR2_R = df,
    p_CR2_R = result$p_Satt,
    ci95_CR2_R_low = b - qt(.975, df) * se,
    ci95_CR2_R_high = b + qt(.975, df) * se
  )
}
write.csv(do.call(rbind, answer), args[2], row.names = FALSE)
writeLines(
  c(
    capture.output(sessionInfo()),
    paste('clubSandwich_path', find.package('clubSandwich')),
    capture.output(packageDescription('clubSandwich'))
  ),
  args[3]
)
