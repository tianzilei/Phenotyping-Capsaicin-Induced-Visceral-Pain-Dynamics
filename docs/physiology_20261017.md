# Physiological model API

`capsaicin.physiology` provides standalone numerical functions without private source locations or run-state dependencies.

| Function | Role |
| --- | --- |
| `prepare(data, outcome, predictors)` | Reject duplicate/nonfinite participant-block observations, retain repeated observations and absorb participant effects |
| `fit(prepared)` | Fixed-effect coefficients, participant-clustered CR1 covariance and leave-one-participant CRV3 sensitivity |
| `wild(prepared, result, replicates=..., seed=...)` | Null-restricted Rademacher bootstrap-t with explicit simulation settings |
| `adjust(values, method)` | BY or BH adjustment within an explicitly supplied comparison set |
| `keep_people`, `standardize` | Repeated-block eligibility and within-participant sample-SD scaling |
| `full_design_check` | Independent explicit-design covariance calculations, including CR2/Satterthwaite |

`scripts/run_physiology.py` fits an explicitly prepared model table into a new external output directory. It performs no raw-record selection, cross-modal matching or signal validation. The old private-container launchers are retired. Independent R covariance code remains under `scripts/physiology_20261017/`.

The independent full-design check expects the outcome column `value` and a predictor list in `data.attrs["predictors"]` before preparation. Other outcomes can use `prepare` and `fit` directly.

The original aggregate 161-comparison and expanded 54-comparison files remain separate. CR1 and CR2 results retain their distinct roles. No historical association was refitted during repository cleanup.
