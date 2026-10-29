# Exploratory physiological inference

The October 17 analysis uses the fixed 215-participant cohort and previously screened measured features. All models require at least two eligible blocks per participant. Complete support requires all five numerical sensation ratings, and missing ratings, E/T, and missing blocks are not filled.

The original evaluation contains 24 sensation–ECG/Hb coefficients, 66 EGG–Hb coefficients, 66 coefficients from 22 joint models, three EGG–sensation coefficients and two paired resting/post-administration cardiac differences. Repeated-block models absorb participant effects and include categorical block effects. CR1 covariance uses G/(G−1) × (N−1)/(N−G−K), with two-sided t(G−1) tests and marginal intervals. The five within-family BY/BH adjustments and all-161 adjustments remain separate. Null-restricted Rademacher wild bootstrap-t uses 19,999 draws for every original 24-target model. CRV3, adjacent differences, timing and Hb quality sensitivities are retained.

The 54-test extension contains the original 24, eight direct left-minus-right Hb contrasts and 22 sensation–Hb coefficients conditional on heart rate. Paired models share observations and scale. CR1 remains the main inference. Explicit full fixed-effect OLS with identity working covariance and clubSandwich 0.7.0 supplies CR2/Satterthwaite sensitivity. BY/BH adjustment is retained within each fixed family and across all 54. It does not replace the separate all-161 evaluation. Common-support timing comparisons retain all 432 positions; two −100 ppm RR-RMSSD positions are duration-ineligible at 299.97 s. Shared-region comparisons are descriptive and retain all coefficients.

Acquisition units, signal extraction, block alignment and quality thresholds are listed in the [measurement contract](measurement_contract.md). Nominal physiological time starts at the selected recording/segment; it is not a verified administration timestamp. Hb coefficients use participant-specific sample SDs, while original instrument exports retain the manufacturer's relative scale.

## Files

- [Frozen original inference configuration](../config/physiology_inference_20261017_v1.json)
- [Frozen extension configuration](../config/physiology_extension_20261017_v1.json)
- [Original aggregate results and checks](../data/aggregate_sources/20261017/physiology_20261017/)
- [Extension aggregate results and checks](../data/aggregate_sources/20261017/physiology_extension_20261017/)
- [Execution programs](../scripts/physiology_20261017/)
- [Environment record](../dependencies/physiology-20261017.json)
- [Code equivalence record](physiology_code_equivalence_20261027.json)

The current numbered export contains the 24-target and all-161 tables in S22/S23 and the extension tables in S25–S29. S18/S19 contain channel assignment and population flow. Table S21 retains the original descriptive bootstrap summaries. Historical candidate `primary_p/q` fields remain unmodified.

## Controlled execution

Set `CAPSAICIN_ANALYSIS_ROOT` to the verified private analysis workspace. Set `CAPSAICIN_PHYSIOLOGY_RUN` and `CAPSAICIN_EXTENSION_RUN` to separate private run directories. New main runs reject existing output directories. Individual outputs must remain outside this publication repository. Optional `CAPSAICIN_INFERENCE_CONFIG` and `CAPSAICIN_EXTENSION_CONFIG` select new locally frozen configurations; defaults identify the published historical scientific choices. Public configurations remove personal absolute locations and retain the relative controlled-input structure and original parameters.

The original inference entry point is `python3 scripts/physiology_20261017/analyse.py`; `sensitivities.py` and `verify_inference.py` operate on that run. The historical verification also expects retained execution logs and the earlier independent v1 reference run alongside the v2 run. The extension entry point is `run_extension.py`, followed by `decompose.py`, the independent R check and `verify_extension.py`. Its `prior_run` must point to the verified original inference, and `CAPSAICIN_PHYSIOLOGY_RUN` must identify the same prior run. The R command is `Rscript scripts/physiology_20261017/check_CR2.R CONTROLLED_MODEL_INPUT.csv NEW_CR2_OUTPUT.csv NEW_ENVIRONMENT_OUTPUT.txt`. Install clubSandwich 0.7.0 in the selected R library; no personal library path is embedded.

These programs expect the original controlled candidate containers, source manifests, reconciled identities and inherited hashes. Aggregate CSVs cannot replace those inputs. Resuming or repeating a historical verification requires its named inputs and new destinations; existing derived files are never silently overwritten. The published integration does not run these real-data programs.

The retained verification summaries describe the completed original runs. Current tests use synthetic participants to independently check the CR1 covariance, multiplicity adjustments, duplicate/rank failures and output guards. Independent signal reference validation, cortical specificity and external prediction are not established by these measured-feature associations.
