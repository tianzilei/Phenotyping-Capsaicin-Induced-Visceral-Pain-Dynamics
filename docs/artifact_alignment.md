# Current artifact numbering and provenance

The current public export is [20261023](../data/published/20261023/README.md), aligned to the October 14, 2026 document revision. It contains four main figures, six supporting figures, three main tables and twenty supporting tables. The statistical results remain those completed through October 4. The earlier [20261004 export](../data/published/20261004/README.md) retains its historical numbering and layout.

## Measurement

The recorded outcome is a custom 0–10 overall sensation score: 0 denotes no discomfort, 1 any discomfort, and 10 an intolerable sensation. Historical VAS field/file names refer to this custom score, which has not been validated as a standard pain or visual analogue scale. E records stopping after two consecutive zero ratings with staff-confirmed absence of discomfort; T records stopping for intolerable sensations rated 10. Actual minutes, numeric zero, missing entries and stopping codes retain their original representation.

## Figure mapping

| Current figure | Earlier figure |
| --- | --- |
| Figure1_temporal_sensation | Figure2_VAS_composition_finite_changes |
| Figure2_temporal_patterns | Figure4_complete_FPCA |
| Figure3_symptoms_regions | Figure3_symptoms_regions_cooccurrence |
| Figure4_future_score_prediction | Figure5_internal_prediction |
| FigureS1_FPCA_stability_reconstruction | FigureS1_FPCA_stability_reconstruction |
| FigureS2_GAMM_numerical_diagnostics | FigureS2_GAMM_numerical_diagnostics |
| FigureS3_candidate_support_diagnostics | FigureS3_candidate_support_diagnostics |
| FigureS4_bounds_all_MC_status | FigureS4_bounds_all_MC_status |
| FigureS5_partition_recovery_baseline | FigureS5_partition_recovery_baseline |
| FigureS6_observation_support | Figure1_observation_support |

The retained final layout uses a width of 165.1 mm, 600 dpi PNG, editable-text SVG and TrueType-embedded PDF. The original plotting implementation is retained in `src/capsaicin/final_figures.py`, with current figure identifiers and pinned formatting. Three aggregate plotting inputs accompany it under `data/aggregate_sources/20261023/`. Their numeric content corresponds to the existing public results. Rendering uses no individual records, model fitting, exclusions, imputation or resampling.

## Table mapping

| Current table | Public aggregate source |
| --- | --- |
| Table 1 | Earlier Table 1 analysis sets and Table S11 baseline descriptions |
| Table 2 | Table S10, three groups, `accuracy_equal_fold_mean`, all 16 interval/prefix/model rows |
| Table 3 | Earlier Table 3 prediction errors and paired differences |
| Table S1 | Earlier 18-module inventory, with final result/configuration references and completed budgets |
| Tables S2–S18 | Earlier tables with the same identifiers and numerical content |
| Table S19 | All 48 `reference_cluster_sizes` entries in the aggregate cluster summary |
| Table S20 | All ten static `ROME_RULES` definitions and `legacy_rule_pattern` counts/proportions in Table S2 |

Current Table 2 concerns early recognition. The earlier `Table2_minute_support_composition_finite_rates.csv` remains a plotting input in the historical export and is not the current main Table 2. Table 2 reports ordinary accuracy; Figure S5 retains its balanced-accuracy summaries. These are separate metrics.

Table S1 distinguishes `historical_planned_replicates` from actual final bootstrap draws and validation repetitions. The completed budgets are read from the published result summaries: 200000 for observed means, symptoms, finite changes and variability; 100000 per complete FPCA interval; 5000 per sparse FPCA, GAMM and clustering specification; 20000 per physiological candidate specification. Prediction, group recognition and baseline development use 20 validation repetitions rather than the historical planned-bootstrap count. Reconstruction also uses 20 repetitions. Complete and sparse FPCA have separate columns. Empty actual-budget fields in blocked or descriptive-only modules do not denote completed inference.

## Reproduction

```sh
python3 -m pip install -r dependencies/requirements-rendering.txt
python3 scripts/build_final_artifacts.py --output NEW_DIRECTORY
```

The versioned configuration checks input hashes before output creation and again after rendering. Existing output directories are refused. `manifest.json` records reviewed input, configuration, implementation and output hashes; `render_manifest.json` records the graphics environment, font hash and rendering settings. `metadata.json` and `qa/text_bounds.json` retain export and layout diagnostics. The input configuration and existing public parameter files preserve their stated scientific scope; this artifact update changes no statistical estimand or fitted result.

The [October 23 publication receipt](artifact_publication_status_20261023.json) identifies the remotely verified artifact commit, fresh-clone audits and successful GitHub workflow.
