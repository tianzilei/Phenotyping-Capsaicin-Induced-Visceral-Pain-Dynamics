# Numerical method interfaces

This reference describes software inputs. Study-specific administration procedures and article text are maintained separately.

| Interface | Required information |
| --- | --- |
| Rating ingestion | Participant key, configured minute columns, numerical limits, missing tokens and stopping tokens |
| Interval statistics | Actual endpoints, required intermediate observations and interval-specific denominator |
| Functional methods | Interval, quadrature weights, centering, retained component count and reconstruction target |
| Prediction | Participant groups, predictors, target horizon, fold counts and error weighting |
| Signal features | Explicit sampling times, units, windows, quality masks and source-selection decisions |
| Repeated-block models | Participant key, block label, outcome, predictors and at least two eligible blocks per participant |
| Resampling | Logical task identity, master seed, replicate numbers and attempt budget |

Signal units and scales must be checked in the supplied input. Software parameter validity does not establish measurement validity. The [code guide](code_guide.md) identifies implementations.
