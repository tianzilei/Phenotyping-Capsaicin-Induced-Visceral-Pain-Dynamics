# Public CRF field contract

This document describes the fields used by the current analysis. The original blank collection form and historical manuscript are preserved in the private pre-update archive. This summary is not a new study protocol, clinical diagnostic instrument or change to collected data.

The investigator confirmed capsaicin exposure of 10% w/v, 10 μL, equivalent to 1 mg. VAS uses 0–10 at actual minutes 1–20. No observed minute-zero VAS is available here. Record numeric zero as zero, missing as missing, and preserve E/T. E denotes stopping after two pain-free minutes; T denotes discontinuation, usually excessive stimulation. The first E/T cell is a recorded minute and cannot substitute for a verified precise event time.

Structured baseline fields cover sex, age, height, weight, BMI, alcohol/spiciness/intake questionnaire fields, CCEI, AES, baseline GI symptoms and time since last meal. Symptom and region code dictionaries are retained under `resources/legacy_codebook/constants.json`. Exact individual demographics and trajectories stay restricted.

`Additional_symptoms` free text and `ACQ_CNP_files` source links are excluded from the random-ID export. Historical calculated fields are preserved only as source values in the restricted archive and are not silently recomputed. Missing code fields are unrecorded; unlisted codes are not clinical negatives. Historical Rome logical matches are not diagnoses.

See [data dictionary](data_dictionary.md) and [privacy handling](data_privacy.md). Any future collection or inference requires its own frozen design/configuration and the relevant scientific and participant-data authorization.
