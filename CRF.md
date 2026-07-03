# Oral Capsaicin Visceral Pain Study CRF

---

## 1. Participant Identification and Collection Information

| Item | Value | Data Entry Variable | Coding/Notes |
|---|---|---|---|
| Participant ID | ______ | ID | Must match data files and ACQ/CNP files |
| Collection date | ______ | collection_date | YYYY-MM-DD |
| Collection start time | ______ | collection_start_time | HH:MM |
| Assessor | ______ | assessor | Name or staff ID |
| Study site | ______ | site | Laboratory/institution |
| Informed consent completed | [ ] Yes [ ] No | consent_completed | The experiment must not proceed without consent |

---

## 2. Demographics and Anthropometrics

| Item | Value | Data Entry Variable | Coding/Notes |
|---|---|---|---|
| Sex | [ ] Female [ ] Male [ ] Other/prefer not to say | Sex | Recommended values: `Female` / `Male` / `Other` |
| Age, years | ______ | Age | Integer or 1 decimal place |
| Height, cm | ______ | Height_cm | 1 decimal place |
| Weight, kg | ______ | Weight_kg | 1 decimal place |
| BMI, kg/m2 | ______ | BMI | May be calculated as Weight_kg/(Height_m^2) |

---

## 3. Pre-Experiment Status

| Item | Value | Data Entry Variable | Coding/Notes |
|---|---|---|---|
| Time since last meal, hours | ______ | Time_since_last_meal_h | Integer hours only, e.g., `3` |
| Alcohol consumption | [ ] Non-drinker [ ] Occasional drinker [ ] Regular drinker | Alcohol_consumption | Recommended values: `Non-drinker` / `Occasional drinker` / `Regular drinker` |
| Baseline gastrointestinal symptoms | [ ] No symptoms [ ] Mild symptoms [ ] Moderate symptoms [ ] Severe symptoms | Baseline_GI_symptoms | Recommended values: `No symptoms` / `Mild symptoms` / `Moderate symptoms` / `Severe symptoms` |
| Baseline symptom description | ______ | baseline_symptom_description | Briefly describe symptoms if present |
| Pre-test fasting/dietary requirements met | [ ] Yes [ ] No | pretest_requirement_met | If no, record the reason |
| Notes | ______ | baseline_notes | Conditions that may affect experimental status |

---

## 4. Habitual Capsaicin Intake Questionnaire (HCIQ)

Please recall your stable dietary habits over the past 12 months.

| Question | Item | Options | Data Entry Variable |
|---|---|---|---|
| Q1 | Average weekly frequency of spicy food intake over the past 12 months | 0=Never; 1=<1 time/week; 2=1-2 times/week; 3=3-4 times/week; 4=>=5 times/week | Spicy_food_frequency |
| Q2 | Usual spiciness level | 1=Not spicy; 2=Mild; 3=Moderate; 4=Spicy; 5=Very spicy | Usual_spiciness_level |
| Q3 | Preference for spicy foods | 1=Strongly dislike; 2=Dislike; 3=Neutral; 4=Like; 5=Strongly like | Spicy_food_preference |
| Q4 | Maximum tolerable spiciness | 1=Very low; 2=Low; 3=Moderate; 4=High; 5=Very high | Max_tolerable_spiciness |
| Q5 | Main sources of spicy foods, select all that apply | [ ] Fresh chili [ ] Dried chili [ ] Chili sauce/oil [ ] Processed spicy foods [ ] Other: ____ | spicy_food_sources |

**CCEI calculation field:** `CCEI = Spicy_food_frequency * Usual_spiciness_level * Spicy_food_preference`.  
`CCEI` is an analysis-derived variable. It may be calculated by the data processing script or manually checked by study staff.

| Derived Variable | Value | Notes |
|---|---:|---|
| CCEI | ______ | Chronic Capsaicin Exposure Index |

---

## 5. Recent/Acute Capsaicin Intake Questionnaire (RAIQ)

Please recall spicy food intake during the 24 hours before the experiment.

| Question | Item | Value | Data Entry Variable | Coding/Notes |
|---|---|---|---|---|
| Q6 | Any spicy food intake in the past 24 hours | [ ] No [ ] Yes | Recent_spicy_intake_24h | 0=No; 1=Yes |
| Q7 | Time since most recent spicy food intake, hours | ______ | Time_since_last_intake_h | Integer hours only; enter `NA` if Q6=No |
| Q8 | Number of spicy food intake episodes in the past 24 hours | ______ | Spicy_episodes_24h | Integer; enter 0 if Q6=No |

If Q8 >= 1, record each episode:

| Episode | Intake Time | Food Type | Spiciness 1-5 | Estimated Portion(s) | Estimated Weight, g | Notes |
|---|---|---|---:|---:|---:|---|
| 1 | ______ | ______ | ___ | ___ | ___ | ______ |
| 2 | ______ | ______ | ___ | ___ | ___ | ______ |
| 3 | ______ | ______ | ___ | ___ | ___ | ______ |
| 4 | ______ | ______ | ___ | ___ | ___ | ______ |

**AES calculation field:** `AES = sum(SpiceIntensity_i * Portions_i)`.  
Each portion may be estimated as 10-20 g of chili or an equivalent spicy condiment. If Q6=No, `AES=0`.

| Derived Variable | Value | Notes |
|---|---:|---|
| AES | ______ | Acute Exposure Score |

---

## 6. ECG/EGG Device Collection Record

This section records raw physiology files and acquisition quality. HRV, EGG spectral features, and ECG-EGG coupling features are generated later from the raw files.

| Item | Value | Data Entry Variable | Coding/Notes |
|---|---|---|---|
| ACQ/CNP file name or path | ______ | ACQ_CNP_files | Separate multiple files with semicolons |
| ECG successfully recorded | [ ] Yes [ ] No | ecg_recorded | If no, explain why |
| EGG successfully recorded | [ ] Yes [ ] No | egg_recorded | If no, explain why |
| Recording duration, seconds | ______ | recording_duration_s | Target duration should follow the protocol |
| ECG lead/channel | ______ | ecg_channel | Device channel name |
| EGG channel | ______ | egg_channel | Device channel name |
| Obvious artifact or signal loss | [ ] None [ ] Present | signal_artifact_observed | If present, specify the time interval |
| Device notes | ______ | physiology_notes | Acquisition problems, missing files, calibration issues |

## 7. Oral Capsaicin Administration Record

| Item | Value | Notes |
|---|---|---|
| Capsaicin batch/source | ______ | Record manufacturer and batch number for food-grade capsaicin |
| Capsaicin dose | ______ mg | Current manuscript protocol: 1 mg |
| Capsule type | ______ | e.g., gastric-soluble gelatin capsule |
| Administration time T0 | ______ | HH:MM:SS |
| Swallowing directly observed by study staff | [ ] Yes [ ] No | If no, explain why |
| Administration completed | [ ] Yes [ ] No | If no, record the reason |
| Water volume | ______ mL | Record if required by the protocol |
| Administration notes | ______ | Coughing, swallowing difficulty, delay, or other issues |

---

## 8. Minute-by-Minute Sensation/VAS Scores Over 20 Minutes

Scoring instructions: 0=no sensation/no pain, 10=strongest imaginable discomfort or pain.  
If the participant stops early, record `E` at the first stopped time point. If stopping is due to a technical or procedural reason, record `T`. After an `E` or `T` marker appears, subsequent time points should not be scored and should be entered as missing.

| Time Point | 1 min | 2 min | 3 min | 4 min | 5 min | 6 min | 7 min | 8 min | 9 min | 10 min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VAS/Sensation Score | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___ |

| Time Point | 11 min | 12 min | 13 min | 14 min | 15 min | 16 min | 17 min | 18 min | 19 min | 20 min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VAS/Sensation Score | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___ | ___ |

Corresponding data entry variables: `VAS_1min` to `VAS_20min`.

| Derived Variable | Value | Notes |
|---|---:|---|
| VAS_Avg. | ______ | Calculated by script or manually checked |
| Peak VAS | ______ | Analysis-derived |
| Time-to-peak, min | ______ | Analysis-derived |
| AUC | ______ | Analysis-derived |

---

## 9. Post-Experiment Overall Sensation, Symptoms, and Regions

| Item | Value | Data Entry Variable | Notes |
|---|---|---|---|
| Overall sensation intensity, 0-10 | ______ | overall_sensation_score | Separate from minute-by-minute VAS; may be used as an overall subjective rating |
| Free-text abdominal/thoracoabdominal discomfort description | ______ | Additional_symptoms | Preserve the original description |
| Main symptom code(s) | ______ | Symptom_codes | Enter A-L only; multiple codes may be concatenated, e.g., `ACG` |
| Main region code(s) | ______ | Region_code | Multiple codes may be concatenated or separated by semicolons, e.g., `25`; `25` may represent 2+5 |

### 9.1 Symptom Codebook

Use the following standardized codes for this study. Data entry must follow this table.

| Code | Symptom | Description |
|---|---|---|
| A | abdominal pain | Abdominal pain |
| B | bloating | Bloating/gas sensation |
| C | abdominal distension | Abdominal fullness or distension |
| D | heartburn | Heartburn |
| E | acid regurgitation | Acid regurgitation |
| F | belching | Belching |
| G | nausea | Nausea |
| H | vomiting | Vomiting |
| I | loss of appetite | Loss of appetite |
| J | tenesmus | Tenesmus |
| K | palpitations | Palpitations |
| L | irritability | Irritability |
| M | other | Other; do not enter into `Symptom_codes`; describe only in `Additional_symptoms` |

### 9.2 Anatomical Region Codebook

Record region codes based on participant marking or description. Multiple regions may be selected and entered as concatenated codes or separated by semicolons.

| Code | Region | Description |
|---|---|---|
| 1 | epigastrium | Epigastrium/subxiphoid area |
| 2 | right hypochondrium | Right hypochondrium |
| 3 | left hypochondrium | Left hypochondrium |
| 4 | umbilical | Umbilical region |
| 5 | hypogastrium | Hypogastrium/suprapubic area |
| 6 | right lumbar | Right lumbar region |
| 7 | left lumbar | Left lumbar region |
| 8 | right inguinal | Right inguinal region |
| 9 | left inguinal | Left inguinal region |

---

## 10. Safety Monitoring and Adverse Events

Expected transient heartburn, abdominal pain, abdominal distension, nausea, or related symptoms should be recorded as study outcomes. Record an adverse event only when symptoms are severe, prolonged, require clinical management, lead to early termination, or exceed the expected response profile.

| Safety Outcome | Result | Notes |
|---|---|---|
| Any adverse event | [ ] No [ ] Yes | any_adverse_event |
| Serious adverse event | [ ] No [ ] Yes | serious_adverse_event |
| Medical intervention required | [ ] No [ ] Yes | medical_intervention_required |
| Protocol discontinuation due to adverse event | [ ] No [ ] Yes | protocol_discontinuation_due_to_ae |

If any adverse event occurs, record each event:

| AE No. | Onset Time | Event Description | Severity | Relatedness to Capsaicin | Duration | Management/Intervention | Outcome |
|---|---|---|---|---|---|---|---|
| AE1 | ______ | ______ | [ ] Mild [ ] Moderate [ ] Severe | [ ] Unrelated [ ] Possible [ ] Probable [ ] Definite | ______ | ______ | ______ |
| AE2 | ______ | ______ | [ ] Mild [ ] Moderate [ ] Severe | [ ] Unrelated [ ] Possible [ ] Probable [ ] Definite | ______ | ______ | ______ |
| AE3 | ______ | ______ | [ ] Mild [ ] Moderate [ ] Severe | [ ] Unrelated [ ] Possible [ ] Probable [ ] Definite | ______ | ______ | ______ |

Early termination record:

| Item | Value |
|---|---|
| Early termination | [ ] No [ ] Yes |
| Termination type | [ ] E=participant/symptom-related reason [ ] T=technical reason |
| First termination time point | ______ min |
| Reason for termination | ______ |
