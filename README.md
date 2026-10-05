# Capsaicin-Induced Visceral Pain Dynamics

This repository contains the analysis framework for studying the time course and heterogeneity of capsaicin-induced visceral pain. The research examines repeated pain ratings alongside recorded symptoms, baseline characteristics, and candidate physiological signals, with an emphasis on observation support, trajectory structure, and prediction from earlier measurements.

The current code and [analysis plan](docs/analysis_plan.md) reflect an exploratory, results-informed reanalysis of an existing cohort, updated through **October 4, 2026**. The [decision log](docs/decision_log.md) records methodological choices and their scope. The plan is not a preregistration; empirical trajectory groups remain research constructs requiring clinical validation.

## Research questions

- How do pain ratings evolve over the observation period, and how much of an apparent time trend reflects changes within participants versus changes in who remains observed?
- Which aspects of trajectory shape, finite changes, and variability describe differences between participants?
- How do recorded symptoms, pain regions, baseline measures, and candidate physiological features relate to pain dynamics?
- How well can earlier ratings predict a later observed rating when evaluation separates participants between training and testing?

## Study design and measurements

The analysis uses an existing cohort of **215 participants** exposed to **10% w/v capsaicin, 10 microlitres (1 mg)**. Pain ratings use a **0–10 visual analogue scale (VAS)** at actual integer minutes **1–20**. Analyses distinguish the early 1–10-minute interval from the extended 1–20-minute interval, and use the participants supported by each target. No measured minute-zero VAS is available.

The observation record includes numeric ratings, missing cells, and two stopping codes: **E** records stopping after two pain-free minutes; **T** records discontinuation, usually because of excessive stimulation. These codes remain separate from numeric scores and pain states. Their first recorded minute does not establish an exact event time. Missing ratings are retained, without zero filling or interpolation across gaps.

Recorded symptom and region codes, demographic and questionnaire fields, and candidate electrocardiographic (ECG), haemoglobin, and electrogastrographic (EGG) measures provide additional analysis domains. The [data dictionary](docs/data_dictionary.md) defines their representation and handling.

## Analysis framework

| Domain | Approach | Target and interpretation |
| --- | --- | --- |
| Observation process | Audit sources and identities; describe minute-specific support, E/T codes, and adjacent mean-change decompositions. | Distinguish within-participant changes from changes in observer composition. Report explicit denominators. |
| Pain time course | Fit Gaussian generalized additive mixed working models with an identity link, cubic regression splines, restricted maximum likelihood, participant random intercepts, and continuous-time first-order autoregressive residual correlation on actual minutes. | Describe smooth trends, with empirical summaries, fit diagnostics, and sensitivity to the time interval, spline basis, and residual correlation. |
| Functional variation | Apply complete-trajectory functional principal component analysis (FPCA) on the raw VAS scale with fixed trapezoidal time weights; examine component and subspace stability. Evaluate sparse FPCA separately. | Characterize variation under the observation support and assumptions of each model. |
| Finite changes and variability | Calculate signed changes and rates over 1-, 2-, and 5-minute spans, adjacent variability, polynomial residual descriptors, and area under the curve. | Require numeric observations throughout each eligible change span; preserve actual adjacency for variability and area calculations. |
| Trajectory grouping | Explore ordinary, fuzzy, and dynamic time warping clustering; assess partition stability and group recovery from short trajectory subsequences (shapelets) or early prefixes. | Study empirical trajectory structure and recovery of training-defined groups. |
| Symptoms and pain regions | Describe marginal codes, co-occurrence, and historical rule patterns using field-specific and joint denominators. | Treat missing fields as unrecorded; rule matching does not establish a clinical diagnosis. |
| Future-rating prediction | Compare persistence, ridge regression, and random forest for the next actual rating and prediction of minute 10 from the minute 5 prefix. | Use 20 repeats of nested participant-level cross-validation, with 5 outer and 4 inner folds and preprocessing fitted within training participants. |
| Candidate physiology | Examine within-participant ECG, haemoglobin, and EGG associations under source, unit, clock, and signal-quality checks. | Keep candidate association analyses separate from independent physiological validation. |

Complete-curve reconstruction, trajectory-group recovery, and future-rating prediction have different evaluation targets. Clinical Markov states, phase/directionality, calibrated instantaneous derivative inference, and external phenotype validation require additional implementation or evidence. Modules marked `interface_only` or `design_only` remain unavailable estimators. The [detailed plan](docs/analysis_plan.md) and [module inventory](config/modules.json) specify each module's current scope.

## Repository structure

| Location | Contents |
| --- | --- |
| [`src/capsaicin/`](src/capsaicin/) and [`R/`](R/) | Data contracts, quality control, descriptive analyses, working models, prediction, and explicit readiness gates. |
| [`config/`](config/) and [`schemas/`](schemas/) | Versioned method parameters, execution contracts, and blank input schemas. |
| [`dependencies/`](dependencies/) and [`renv.lock`](renv.lock) | Python and R environment records. |
| [`tests/`](tests/) | Synthetic fixtures and tests for ingestion, analysis contracts, and release integrity. |
| [`data/aggregate_sources/20261004/`](data/aggregate_sources/20261004/) | Reviewed aggregate inputs for public figure and table rendering. |
| [`data/published/20261004/`](data/published/20261004/) | Aggregate figures and tables. |
| [`docs/`](docs/) | Analysis plan, methodological decisions, data definitions, code guide, and reproducibility records. |

The [code style guide](docs/code_style.md) defines formatting and contributor checks. The [code guide](docs/code_guide.md) maps analysis domains to their implementations and explains which tasks require controlled participant data or additional execution infrastructure.

## Data and supporting material

The public repository contains code, synthetic examples, and reviewed aggregate outputs. Real participant records and identity mappings remain outside Git; [data handling](docs/data_privacy.md) documents their treatment. The [release inventory](docs/release_inventory.json) records source and published file hashes.

Aggregate outputs are listed in the [artifact index](data/published/20261004/README.md), with full-precision [tables](data/published/20261004/tables/) and a [figure review PDF](data/published/20261004/figure_review.pdf).
