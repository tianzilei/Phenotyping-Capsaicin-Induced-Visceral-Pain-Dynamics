# Capsaicin-Induced Visceral Pain Dynamics

[![Public release checks](https://github.com/tianzilei/Phenotyping-Capsaicin-Induced-Visceral-Pain-Dynamics/actions/workflows/public-release.yml/badge.svg)](https://github.com/tianzilei/Phenotyping-Capsaicin-Induced-Visceral-Pain-Dynamics/actions/workflows/public-release.yml)

Analysis code, method configurations and public aggregate results for studying the time course and individual variation of responses to an oral capsaicin challenge. The analyses cover overall sensation ratings, symptoms and perceived regions, trajectory structure, early group recognition, later-score prediction and exploratory physiological measurements.

This is an exploratory, results-informed reanalysis of an existing cohort. The [analysis plan](docs/analysis_plan.md) describes its scientific scope, and the [decision log](docs/decision_log.md) records methodological choices. The plan is not a preregistration.

## Current public release

The **October 23, 2026 export** follows the numbering in the **October 14, 2026 document revision** and uses analysis results completed through **October 4, 2026**. It contains **4 main figures, 6 supporting figures, 3 main tables and 20 supporting tables**.

| Resource | Contents |
| --- | --- |
| [Current figures and tables](data/published/20261023/README.md) | Complete numbered index with PNG, PDF, SVG and CSV files |
| [CSV tables](data/published/20261023/tables/) | Cohort and analysis sets; early three-group recognition; future-score errors; Tables S1–S20 |
| [Figure numbering and sources](docs/artifact_alignment.md) | Mapping from the earlier export and the aggregate sources behind each table |
| [Reproduction guide](docs/reproducibility.md) | Rendering environment, input hashes and controlled-analysis prerequisites |
| [Publication receipt](docs/artifact_publication_status_20261023.json) | Verified artifact commit, independent-clone checks and GitHub workflow result |

The main figures show [temporal sensation and finite changes](data/published/20261023/figures/Figure1_temporal_sensation.png), [functional trajectory patterns](data/published/20261023/figures/Figure2_temporal_patterns.png), [symptoms and perceived regions](data/published/20261023/figures/Figure3_symptoms_regions.png), and [future-score prediction](data/published/20261023/figures/Figure4_future_score_prediction.png).

The [October 4 export](data/published/20261004/README.md) retains its earlier numbering and layout. In the current export, **Table 2 describes early group recognition**, and the observation-support plot is **Figure S6**. Table S19 provides all 48 reference group-size specifications; Table S20 provides all ten descriptive symptom-region rules. Table S1 separates historical plans from completed resampling budgets and validation repetitions.

## Study and measurements

The reconciled cohort contains **215 participants** and **3,424 numerical ratings**. Each participant received **10 microlitres of a 10% w/v capsaicin preparation, equivalent to 1 mg**. Ratings were scheduled at actual integer minutes **1–20**. Complete minutes 1–10 are available for **206 participants** and complete minutes 1–20 for **56**.

The recorded outcome is a **custom 0–10 overall sensation score**: 0 denotes no discomfort, 1 any discomfort, and 10 an intolerable sensation. It has not been validated as a standard pain or visual analogue scale. Historical `VAS` field and file names refer to this custom score. No numerical minute-zero rating is available.

**E** records stopping after two consecutive zero ratings with staff-confirmed absence of discomfort; **T** records discontinuation for intolerable sensations rated 10. Numerical ratings, E, T and missing entries remain separate. First recorded codes are recording markers rather than verified exact event times. Missing minutes and post-stop scores are left unfilled.

Symptom and perceived-region information is available for **209 participants per field**, with **204** having both. The [data dictionary](docs/data_dictionary.md) and [field contract](docs/field_contract.md) describe score cells, symptom/region codes, baseline measures and candidate physiological inputs.

## Analyses

| Domain | Implementation and target |
| --- | --- |
| Observation support | Minute-specific denominators, E/T counts, and decomposition of observed mean changes into paired changes and observation-composition terms |
| Sensation time course | Gaussian identity-link additive mixed working models with cubic regression splines, REML, participant random intercepts and actual-time CAR1 residual correlation, with numerical diagnostics and sensitivities |
| Functional variation | Complete-trajectory FPCA on the original score scale with trapezoidal weights; component/subspace stability, retrospective reconstruction and separate sparse-FPCA sensitivities |
| Finite changes and variability | Signed changes over 1-, 2- and 5-minute spans, adjacent variability, polynomial residual descriptions and area under the curve; required observations preserve actual adjacency |
| Trajectory groups | Ordinary, fuzzy and dynamic-time-warping grouping, partition stability, and recovery of training-defined groups from early prefixes or training-selected shapelets |
| Symptoms and regions | Marginal codes, all symptom-region co-occurrences and descriptive historical rule matches, with field-specific and joint denominators |
| Future-score prediction | Last-value, ridge and random-forest comparisons using 20 repetitions of nested participant validation: 5 outer and 4 inner folds, with preprocessing fitted within training participants |
| Candidate physiology | Exploratory ECG, haemoglobin and EGG analyses with source, unit, clock and quality checks; independent physiological validation remains required |

Next-rating prediction uses **2,781 eligible targets from 213 participants**. Prediction of minute 10 from minutes 1–5 uses **206 participants**. Complete-curve reconstruction, trajectory-group recovery and future-score prediction have separate evaluation targets. Empirical groups and descriptive symptom-rule matches do not establish clinical phenotypes or diagnoses. Resampling ranges and validation-repeat ranges retain their stated descriptive roles.

The [18-module inventory](config/modules.json) identifies implemented analyses and remaining scientific gates. Modules marked `interface_only` or `design_only` remain unavailable estimators. External phenotype validation, calibrated instantaneous derivatives, clinical Markov states and phase/directionality inference require further implementation or evidence.

## Reproduce the public figures and tables

Use Python **3.12.13** and the retained graphics package versions:

```sh
python3 -m pip install -r dependencies/requirements-rendering.txt
python3 scripts/build_final_artifacts.py --output NEW_DIRECTORY
```

Choose a new output directory. The builder checks reviewed input hashes before and after rendering and exports the current figures, 23 CSV tables, figure index, layout diagnostics and provenance manifests. It uses public aggregates without participant records, model fitting or new resampling. PNGs use 600 dpi; PDFs embed TrueType fonts; SVGs retain editable text. Font and software differences can affect rendered bytes across systems.

The [versioned artifact configuration](config/final_artifacts_20261023_v1.json) identifies the inputs and numbering. The plotting implementation is in [final_figures.py](src/capsaicin/final_figures.py), and [final_artifacts.py](src/capsaicin/final_artifacts.py) exports the numbered tables. The historical renderer, [build_scientific_figures.py](scripts/build_scientific_figures.py), reproduces the earlier October 4 export.

## Repository structure

| Location | Contents |
| --- | --- |
| [`src/capsaicin/`](src/capsaicin/) and [`R/`](R/) | Data contracts, quality control, descriptive analyses, working models, prediction and readiness gates |
| [`config/`](config/) and [`schemas/`](schemas/) | Versioned method parameters, execution contracts and blank input schemas |
| [`dependencies/`](dependencies/) and [`renv.lock`](renv.lock) | Python and R environment records |
| [`tests/`](tests/) | Synthetic ingestion, analysis-contract and release-integrity tests |
| [`data/aggregate_sources/20261004/`](data/aggregate_sources/20261004/) | Reviewed aggregate analysis results |
| [`data/aggregate_sources/20261023/`](data/aggregate_sources/20261023/) | Retained aggregate inputs for the final figure layout |
| [`data/published/20261023/`](data/published/20261023/) | Current numbered figures and tables |
| [`docs/`](docs/) | Analysis plan, code guide, data definitions, reproduction instructions and publication records |

The [code guide](docs/code_guide.md) maps analysis domains to their implementations. [Code style](docs/code_style.md) documents contributor checks.

## Data access and verification

Public content includes code, method configurations, blank schemas, synthetic examples and reviewed aggregate outputs. Participant-level ratings, symptom-region records, identity mappings and original physiological signals require controlled access. [Data handling](docs/data_privacy.md) explains their treatment. Running individual-level analyses requires the relevant controlled inputs, provenance checks, execution configuration and Python/R environment.

The [October 23 verification record](docs/artifact_alignment_verification_20261023.json) documents **318 passing synthetic tests**, ten PNGs matching the target figures byte for byte, and all 74 rows/rules in the three newly exported tables matching their existing aggregate sources. The [release inventory](docs/release_inventory.json) records source and published file hashes. Current GitHub checks are linked in the badge above; the [publication receipt](docs/artifact_publication_status_20261023.json) records the verified artifact revision and its independent-clone checks.
