# Gastrointestinal sensations after oral capsaicin

[![Public release checks](https://github.com/tianzilei/Phenotyping-Capsaicin-Induced-Visceral-Pain-Dynamics/actions/workflows/public-release.yml/badge.svg)](https://github.com/tianzilei/Phenotyping-Capsaicin-Induced-Visceral-Pain-Dynamics/actions/workflows/public-release.yml)

Analysis code, method configurations and public aggregate results accompanying **Gastrointestinal sensation trajectories and symptom profiles after oral capsaicin in healthy volunteers**. The measured outcome is overall gastrointestinal sensation after a single oral capsaicin exposure. The analyses cover overall sensation ratings, symptoms and perceived regions, trajectory structure, early group recognition, later-score prediction and exploratory physiological measurements.

This is an exploratory, results-informed reanalysis of an existing cohort. The [analysis plan](docs/analysis_plan.md) describes its scientific scope, and the [decision log](docs/decision_log.md) records methodological choices. The plan is not a preregistration.

## Current release

The final DOCX pair was checked on **October 29, 2026** against the **October 27, 2026 export**, which includes analysis results completed through **October 17, 2026**. All 31 accompanying CSV tables and all ten embedded PNG figures match the retained export byte for byte. It contains **4 main figures, 6 supporting figures, 2 main tables and 29 supporting tables**.

| Resource | Contents |
| --- | --- |
| [Current figures and tables](data/published/20261027/README.md) | PNG, editable SVG/PDF plots and all 31 numbered CSV tables |
| [Figure and table alignment](docs/artifact_alignment.md) | Current numbering and correspondence with earlier exports |
| [Physiological inference](docs/physiology_20261017.md) | 161-test evaluation, 54-test extension, CR1/CR2 and controlled-input execution |
| [Reproduction guide](docs/reproducibility.md) | Aggregate rendering, input hashes and individual-analysis prerequisites |
| [Final document alignment checks](docs/document_alignment_verification_20261029.json) | Document hashes, table and figure comparisons, and local checks |
| [Measurement and acquisition contract](docs/measurement_contract.md) | Rating origin, response coding, signal units, processing and observation requirements |
| [October 27 integration checks](docs/artifact_alignment_verification_20261027.json) | Earlier export and synthetic verification |

Main Table 2 reports future-score prediction; early three-group recognition is Table S16. The observation-support plot is Figure S1. Tables S22–S23 retain the physiological inference, and Tables S25–S29 retain bilateral, heart-rate-conditioned, covariance and timing sensitivities. Original native PNGs are retained exactly; SVG and PDF plots are generated from the same reviewed aggregates.

The [October 23](data/published/20261023/README.md) and [October 4](data/published/20261004/README.md) exports preserve their historical numbering and results. The retained 18-module inventory belongs to those historical analyses; current Table S1 describes analysis subsets.

## Study and measurements

The reconciled cohort contains **215 participants** and **3,424 numerical ratings**. Each participant received **10 microlitres of a 10% w/v capsaicin preparation, equivalent to 1 mg**. Ratings were scheduled at actual integer minutes **1–20**. Complete minutes 1–10 are available for **206 participants** and complete minutes 1–20 for **56**.

The recorded outcome is a **custom 0–10 overall sensation score**: 0 denotes no discomfort, 1 any discomfort, and 10 an intolerable sensation. It has not been validated as a standard pain or visual analogue scale. Historical `VAS` field and file names refer to this custom score. The rating clock starts after the water used to swallow the capsule has been finished; the first scheduled rating is at minute 1. No numerical minute-zero rating is available.

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
| Exploratory physiology | Participant/block fixed-effect models of measured ECG, haemoglobin and EGG features; CR1 intervals and BY/BH correction, CRV3/wild/CR2 sensitivities, bilateral and HR-conditioned comparisons; independent signal validation remains required |

Next-rating prediction uses **2,781 eligible targets from 213 participants**. Prediction of minute 10 from minutes 1–5 uses **206 participants**. Complete-curve reconstruction, trajectory-group recovery and future-score prediction have separate evaluation targets. Empirical groups and descriptive symptom-rule matches do not establish clinical phenotypes or diagnoses. Resampling ranges and validation-repeat ranges retain their stated descriptive roles.

The [18-module inventory](config/modules.json) identifies implemented analyses and remaining scientific gates. Modules marked `interface_only` or `design_only` remain unavailable estimators. External phenotype validation, calibrated instantaneous derivatives, clinical Markov states and phase/directionality inference require further implementation or evidence.

## Reproduce the public figures and tables

Use Python **3.12.13** and the retained graphics package versions:

```sh
python3 -m pip install -r dependencies/requirements-rendering.txt
python3 scripts/build_final_artifacts.py --output NEW_DIRECTORY
```

Choose a new output directory. The builder checks reviewed input hashes before and after rendering and exports the current figures, 31 CSV tables, figure index, layout diagnostics and provenance manifests. It uses public aggregates without participant records, model fitting or new resampling. PNGs use 600 dpi; PDFs embed TrueType fonts; SVGs retain editable text. Font and software differences can affect rendered bytes across systems.

The [versioned artifact configuration](config/aligned_artifacts_20261027_v1.json) identifies the inputs and numbering. The plotting implementation is in [final_figures.py](src/capsaicin/final_figures.py), and [aligned_artifacts.py](src/capsaicin/aligned_artifacts.py) exports the numbered tables. The historical renderer, [build_scientific_figures.py](scripts/build_scientific_figures.py), reproduces the earlier October 4 export.

## Repository structure

| Location | Contents |
| --- | --- |
| [`src/capsaicin/`](src/capsaicin/) and [`R/`](R/) | Data contracts, quality control, descriptive analyses, working models, prediction and readiness gates |
| [`config/`](config/) and [`schemas/`](schemas/) | Versioned method parameters, execution contracts and blank input schemas |
| [`dependencies/`](dependencies/) and [`renv.lock`](renv.lock) | Python and R environment records |
| [`tests/`](tests/) | Synthetic ingestion, analysis-contract and release-integrity tests |
| [`data/aggregate_sources/20261004/`](data/aggregate_sources/20261004/) | Reviewed aggregate analysis results |
| [`data/aggregate_sources/20261023/`](data/aggregate_sources/20261023/) | Retained aggregate inputs for the final figure layout |
| [`data/aggregate_sources/20261017/`](data/aggregate_sources/20261017/) | Exploratory physiological aggregates and verification summaries |
| [`data/aggregate_sources/20261027/`](data/aggregate_sources/20261027/) | Current definition tables, physiological tables and native images |
| [`data/published/20261027/`](data/published/20261027/) | Current numbered figures and tables |
| [`docs/`](docs/) | Analysis plan, code guide, data definitions, reproduction instructions and publication records |

The [code guide](docs/code_guide.md) maps analysis domains to their implementations. [Code style](docs/code_style.md) documents contributor checks.

## Data access and verification

Public content includes code, method configurations, blank schemas, synthetic examples and reviewed aggregate outputs. Individual rating and symptom records, source signals and identifier maps remain under controlled access. [Data handling](docs/data_privacy.md) describes the access requirements. Individual analyses need verified inputs, a frozen local configuration and the recorded Python/R environment. Manuscript and supplementary body prose are excluded from this repository.

The [October 29 verification record](docs/document_alignment_verification_20261029.json) identifies the final source documents by hash and records the current alignment and local checks. The [October 27 verification record](docs/artifact_alignment_verification_20261027.json) retains the earlier export checks. The [release inventory](docs/release_inventory.json) records original and public file hashes. Prior dated publication receipts retain their original scope. This revision is prepared for a user-managed push; no new remote-publication success is claimed.
