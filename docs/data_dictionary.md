# Data dictionary

| Field or artifact | Meaning | Handling |
| --- | --- | --- |
| `ID` | Subject key; `SYN...` in public examples, random `P_...` in restricted copies | Private mappings never enter Git |
| `VAS_1min` … `VAS_20min` | Scheduled actual-minute cells, VAS 0–10 | Keep original strings, missing tokens and E/T |
| Numeric `0` | Observed zero rating | Never treat as missing or synthesize baseline zeros |
| `E` | Stopping after two pain-free minutes | Code, not a score, state or exact event time |
| `T` | Discontinuation, usually excessive stimulation | Separate from E; no filling |
| Empty/`NA`/`N/A`/`NaN` | Missing representation under the input contract | Preserve source token; do not invent observations |
| `Sex`, `Age`, height/weight/BMI | Recorded baseline demographic/body measures | Quasi-identifiers; individual values restricted |
| Intake, spiciness, `CCEI`, `AES`, GI baseline fields | Recorded questionnaire/intake fields | Do not repair without documented evidence |
| `Region_code`, `Symptom_codes` | Recorded coded sets | See `resources/legacy_codebook/constants.json`; missing field is unrecorded |
| `Additional_symptoms` | Potentially identifying free text | Removed from pseudonymized export |
| `ACQ_CNP_files` | Device/source filename links | Removed from pseudonymized export |
| `source_subject` in old shapelets | Array position in the old algorithm | Removed; identity cannot be inferred from the index |
| `cell`, `cell_id` in aggregate tables | Model/parameter cell identifier | Not a participant identifier |
| `people`, `eligible_people` | Target-specific observed support | Do not substitute total cohort size |
| `primary_p`, `primary_q` | Gated physiological inferential fields | NULL in the current candidate analyses |
| `MC_PRECISION_MET` / `MC_PRECISION_INSUFFICIENT` | Endpoint calculation precision status | Does not establish scientific validity or absence of an effect |

Blank templates under `schemas/` define interfaces; they do not certify input provenance, measurement units, artifact QC or scientific readiness. `data/aggregate_sources/20261004/` contains only aggregate rendering inputs, not raw or subject-level records. All reported numeric values retain their original precision.
