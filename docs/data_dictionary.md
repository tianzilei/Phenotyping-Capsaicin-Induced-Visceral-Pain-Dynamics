# Data dictionary

| Field | Type and interpretation |
| --- | --- |
| `ID`, `subject_id`, `person_id` | Participant key; real keys remain restricted; public fixtures use synthetic identifiers |
| `VAS_<minute>min` | Historical field name for a numerical rating at an actual integer minute |
| Numeric zero | Observed numerical value |
| `E`, `T` | Distinct categorical stopping markers |
| Empty/NA tokens | Unrecorded entry under the selected input contract |
| Symptom/region fields | Recorded categorical sets; missing and unlisted categories have different meanings |
| `cell`, `cell_id`, `test_id` | Model or parameter-set identifier, not a participant key |
| `people`, `eligible_people`, `n_people` | Target-specific participant count |
| `blocks`, `n_blocks` | Eligible repeated-observation count |
| `beta`, standard errors, interval endpoints | Coefficient and uncertainty on the table's stated scale |
| `p_CR1`, `p_CR2_R`, `q_*` | Estimator-specific tests and separately defined multiplicity families |
| `MC_PRECISION_*` | Precision of resampling quantile calculations |

Aggregate tables retain their own columns and units. Model identifiers are consistent serial labels across related files. Historical gated `primary_p` and `primary_q` fields remain unfilled where inference was unavailable.

See [input contracts](field_contract.md), [methods](analysis_plan.md) and [restricted-data handling](data_privacy.md).
