# Current exploratory analysis plan — public edition 2026-10-05

This document summarizes the completed, data-supported analysis as of 2026-10-04. It replaces the old publication pipeline as the current entry point. The upstream plan describes additional, results-informed analyses of an existing cohort; it is not a preregistration. Draft parameters are not automatically frozen scientific decisions. The original private plan and decision log are retained with source hashes in `release_inventory.json`; individual adjudications are not reproduced here.

## Population, scale and observed support

The current identity-aware cohort has 215 people and 3,424 numeric VAS ratings at actual integer minutes 1–20 on the 0–10 scale. Complete minutes 1–10 include 206 people; complete 1–20 include 56. There is no measured minute-zero VAS in the published analysis input. Do not fabricate a baseline value. Investigator-confirmed dose is 10% w/v × 10 μL = 1 mg.

E records stopping after two pain-free minutes; T records discontinuation, usually excessive stimulation. Preserve codes and later missing cells separately. The first code column is a recorded minute, not a verified precise stop time or the start of a pain-free interval. Neither mechanism justifies random missingness, zero filling or last-observation carry-forward.

The primary descriptive target is the VAS process among people actually observed at each minute. A full-cohort counterfactual 20-minute trajectory is not identified without assumptions. Complete cases, observed-pair composition decompositions and scale-bounded algebraic ranges have different targets and are labelled separately.

## Implemented analyses

1. Observed support, code counts and baseline descriptors use explicit denominators. The 19 adjacent mean-change decompositions distinguish common-observer changes and population composition; they do not estimate a causal dropout effect.
2. Finite interval changes use spans of 1, 2 and 5 minutes within minutes 1–20. Every intervening actual minute must be numeric. There are 52 eligible spans × 7 statistics = 364 targets. Changes and rates are signed VAS and VAS/minute respectively; they are not instantaneous derivatives. Each span has its own observed support.
3. Raw variation and low-order polynomial residual descriptors retain actual adjacent pairs. AUC and MSSD do not bridge a missing minute. These descriptors do not separate latent instability from measurement error.
4. Complete-trajectory FPCA uses the raw scale and fixed trapezoidal minute weights; report 1–4 components and stability diagnostics. The latest independent run uses 100,000 whole-person resamples per interval, without pooling the older 5,000 draws. Sparse FPCA remains a working model for incomplete observations, without identified dropout correction. Whole-curve test projection measures reconstruction, not future prediction.
5. GAMM fits are Gaussian identity working models using `cr` smooths, REML and a random intercept; CAR1 uses actual minutes, with separately labelled independent-error and k/interval sensitivities. Numerical covariance warnings remain visible. Significant derivative intervals have not passed the required independent calibration and are withheld.
6. Recorded symptom/region codes have denominators of 209 for each marginal field and 204 for jointly recorded fields. Include all 12 symptoms, 9 regions, 108 pairs, and 10 historical rule patterns = 139 statistics. A missing field is unrecorded; an unlisted code is not a clinical negative. Rule matching is not a Rome diagnosis.
7. Future-rating tasks are next actual rating (213 people, 2,781 eligible windows) and minute 5 prefix to minute 10 (206 people). Persistence, ridge and random forest are evaluated in 20 repeats of 5-fold outer/4-fold inner subject-level splits. Fit preprocessing within training subjects. Next-rating window-equal weighting is primary with person-equal sensitivity; 5→10 uses person-equal weighting. Person-equal RMSE is `sqrt(mean(person MSE))`.
8. Cluster/shapelet recovery and baseline prediction remain development analyses. Baseline development has 21 people for 1–10 minutes and 6 for 1–20. Missing classes and incomplete repeats are retained. Do not name them validated clinical phenotypes or sealed-set performance.
9. Physiological candidate analyses contain 112 model cells and 178 coefficient/SSE statistics. Their primary p/q values remain NULL. They do not establish accepted physiological features, independent mechanisms, phase directionality or future predictive gains.

## Frozen execution and uncertainty

Method configurations and dependency locks are versioned. Public parameter copies with generalized site paths are documented by both original and published hashes. They require a new local configuration with the controlled input, confirmed identities, target population and relevant scientific gates before inference. Format-only `validation_20261005_v1.json` does not authorize inference.

Resampling uses whole subjects. New symptoms and finite changes each used a fixed 200,000 draws; FPCA precision uses 100,000 per interval; other modules retain their own 5,000, 20,000 or 200,000 budgets. Failures and undefined statistics are not replaced with successful draws. Quantile endpoints are q.025–q.975 descriptive ranges; MC assessment concerns calculation precision, not population coverage. Both absolute and range-width-relative precision targets apply. The relative width is q.975−q.025, not an IQR or fraction of the point estimate.

MC targets were met for 135/139 recorded-code statistics and 336/364 finite-change statistics; the remaining 4 and 28 are kept. Complete FPCA meets 12/24 targets, GAMM curve endpoints 0/120. All 1,255 unique current MC statistics are published, excluding the superseded older 24 complete-FPCA targets. Twenty prediction training/split min–max ranges are sensitivity summaries, not confidence intervals.

## Scientific conditions still unmet

Independent physiology reference/QC, source units/clocks, calibrated instantaneous derivative inference, clinical Markov states and implementation, phase/directionality, external prediction and clinical phenotype validation remain unmet. Sealed validation has not been opened. Interface-only or design-only code must continue to reject unsupported inference; no invented estimates may replace an error. The full 18-module status is [Table S1](../data/published/20261004/tables/TableS1_all18_modules.csv).
