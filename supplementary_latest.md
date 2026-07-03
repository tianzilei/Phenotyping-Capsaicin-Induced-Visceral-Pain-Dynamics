# Supplementary Appendix

**Supplementary Material for:** "Temporal Dynamics and Phenotypic Heterogeneity in Oral Capsaicin-Induced Human Visceral Pain"

This appendix provides expanded methods and supporting figures and tables that are not displayed directly in the main-text composite figures.

Final retained supplementary scope: Supplementary Methods S1-S2, Figures S1-S5, and Tables S1-S4.

Citation numbers in this appendix follow the main manuscript reference list.

## Supplementary Methods

### S1. Early-window temporal phenotype classification

The analysis framed early-window classification as a subject-level phenotype-prediction task. The baseline-only dataset used the same baseline demographic and questionnaire-derived exposure-history and symptom features, together with electrocardiographic (ECG), electrogastrographic (EGG), and ECG-EGG coupling features, as the main phenotype-prediction analysis. Additional datasets appended the first 3, 5, 8, or 20 minutes of post-capsaicin VAS data.

For each early window, retained predictors included the raw minute-level VAS values and derived summary variables: mean, minimum, maximum, last value, prefix area under the curve, range, linear slope, early delta, and within-prefix peak time. Values marked `E` or `T` were treated as censored; once either marker appeared, all subsequent VAS values for that participant were set to missing before feature extraction.

Candidate classifiers included sparse logistic regression, standard logistic regression, radial and linear support vector machines, ridge classification, k-nearest neighbors, random forest, extra trees, histogram-based gradient boosting, and Gaussian naive Bayes. Stratified ten-fold cross-validation estimated performance. Out-of-fold predictions provided accuracy, balanced accuracy, macro F1, and weighted F1.

The design was prefix-based. At each evaluation horizon, the models used only information available up to that time point. The task assessed how quickly phenotype-relevant trajectory structure emerged, not how well full-trajectory summaries could be reconstructed retrospectively. In practical terms, it asked when the observed signal became informative enough to distinguish delayed-peak, early-sustained, and late-rising response patterns.

### S2. Expanded baseline-plus-physiology phenotype prediction

The baseline phenotype-prediction matrix contained demographic variables, questionnaire-derived exposure-history and symptom variables, ECG features, EGG features, and ECG-EGG coupling features. Questionnaire-derived variables included age, sex, body mass index, height, weight, alcohol consumption, spicy food frequency, usual spiciness level, spicy food preference, maximum tolerable spiciness, Chronic Capsaicin Exposure Index (CCEI), Acute Exposure Score (AES), recent spicy food intake, time since last spicy intake, spicy episodes in the previous 24 hours, baseline gastrointestinal symptom burden, and time since last meal.

ECG-derived variables included heart-rate-variability and signal-quality measures. EGG-derived variables included dominant frequency, power, rhythm-band proportions, entropy, flatness, instability, and signal-quality indices. ECG-EGG coupling variables included cross-correlation, lag, coherence, energy ratio, and heart rate-EGG correlation summaries. Missing values were imputed with column medians.

The primary model set included class-balanced logistic regression, class-balanced random forest, gradient boosting, histogram-based gradient boosting, multilayer perceptron with early stopping, and a stacking ensemble. Stratified ten-fold cross-validation estimated model performance, with balanced accuracy and macro F1 as the primary metrics. A complementary classifier family used the same encoded matrix to generate supplementary feature-importance and confusion-matrix summaries.

These analyses tested whether pre-exposure trait-like information could predict temporal phenotype membership without the evolving pain trajectory. The feature matrix is a heterogeneous baseline descriptor set, not a mechanistically unified biomarker panel. The supplementary feature-importance outputs rank variables that contributed within the fitted models; they do not identify stable causal determinants of phenotype membership.

## Supplementary Results

This appendix retains analyses that extend, rather than duplicate, the main-text composite figures.

### S3. Additional baseline-plus-physiology phenotype summaries

**Figure S1. Age by Phenotype.**

![Figure S1. Age by Phenotype.](data/figures/figure7_age_by_phenotype.png)

*Caption:* Age distributions stratified by temporal phenotype.

Age distributions overlapped across delayed-peak, early-sustained, and late-rising phenotypes.

This matched the broader baseline-prediction result: age alone did not organize the time-based phenotypes identified here.

**Figure S2. Standardized ECG/EGG Feature Distributions.**

![Figure S2. Standardized ECG/EGG Feature Distributions.](data/figures/figure8_ecg_egg_features.png)

*Caption:* Standardized ECG and EGG feature distributions across temporal phenotypes. Abbreviations: ECG, electrocardiographic; EGG, electrogastrographic; HR, heart rate; SDNN, standard deviation of normal-to-normal intervals; LF/HF, low-frequency/high-frequency power ratio.

Feature distributions showed partial between-cluster differences with substantial overlap.

Visual separation in a subset of features did not translate into strong multivariable phenotype classification, indicating that the available physiological feature set was insufficient to recover the temporal phenotypes with high accuracy.

### S4. Local temporal motifs

**Figure S3. Cluster-specific shapelets.**

![Figure S3. Cluster-specific shapelets.](data/figures/figure11_shapelets.png)

*Caption:* Sub-figures are arranged by phenotype in rows and by shapelet rank in columns. Each panel shows one cluster-discriminative shapelet illustrating a local temporal motif for the delayed-peak, early-sustained, or late-rising phenotype. The solid line marks the highlighted shapelet, the dashed line shows the full source trajectory, and the shaded region marks the post-capsaicin time window spanned by the shapelet. AUC denotes the one-vs-rest area under the receiver operating characteristic curve, `d` denotes Cohen's d effect size, and `t` denotes the post-capsaicin time window in minutes.

Delayed-peak responders showed motifs with deferred maxima followed by decline, early-sustained responders showed plateau-like motifs, and late-rising responders showed gradual upward fragments.

These local motifs help explain why DTW-based clustering separated the phenotypes even when full-length trajectories overlapped in absolute intensity at some time points. Discriminative information was partly embedded in short contiguous subsequences, beyond global peak value or total pain burden.

### S5. Symptom-region and Rome IV-informed supplementary visualizations

**Table S1. Top Symptom-Region Associations of the Overall Symptom-Region Network**

| Symptom | Region | Weight |
|:--|:--|--:|
| abdominal distension | right hypochondrium | 110 |
| abdominal distension | hypogastrium | 59 |
| abdominal pain | right hypochondrium | 53 |
| nausea | right hypochondrium | 52 |
| nausea | hypogastrium | 47 |

**Table S2. Top Network Nodes of the Overall Symptom-Region Network**

| Node | Type | Degree | Weighted Degree |
|:--|:--|--:|--:|
| right hypochondrium | region | 12 | 368 |
| hypogastrium | region | 12 | 267 |
| abdominal distension | symptom | 8 | 240 |
| nausea | symptom | 9 | 145 |
| abdominal pain | symptom | 7 | 143 |

Tables S1 and S2 add a network summary that the heatmaps alone do not fully convey. The dominant regions stood out not because of a single symptom pairing, but because they combined broad connectivity with high recurrence. The right hypochondrium and hypogastrium each connected to many symptom categories, and their weighted degrees show that those links also recurred frequently across participants. Likewise, abdominal distension ranked highly not only because it was common, but because it bridged multiple reported regions rather than remaining confined to a single location.

Degree reflects how widely a node participated across symptom-region combinations, whereas weighted degree reflects how often those combinations recurred in the cohort. Together, these rankings show that the capsaicin response pattern was organized around a small set of recurrent symptom-region hubs rather than dispersed evenly across all possible pairings. The network view therefore complements the trajectory analyses by showing that heterogeneity was organized not only across time, but also across symptom quality and perceived anatomical distribution.

**Figure S4. Temporal phenotype to symptom-region-Rome IV flow structure.**

![Figure S4. Temporal phenotype to symptom-region-Rome IV flow structure.](data/figures/figure14_network_sankey.png)

*Caption:* Flow widths represent participant-level symptom-region co-occurrence counts expanded within each temporal phenotype and linked to the participant's top Rome IV-informed category. To preserve readability, lower-frequency symptoms, regions, and Rome-pattern categories were grouped into `Other` nodes. Rome-pattern labels report participant-level `n (%)` together with flow counts. Label abbreviations: `Abd Pain`, abdominal pain; `R-Hypo`, right hypochondrium; `Hypo`, hypogastrium; `L-Hypo`, left hypochondrium; `R-Lumb`, right lumbar. `No Match` indicates that no Rome IV-informed category was assigned by the rule-based mapping.

The Sankey view emphasizes that the three temporal phenotypes did not differ only in trajectory shape. All phenotypes fed strongly into abdominal distension, nausea, and abdominal pain, but the downstream region and Rome-pattern distributions remained concentrated around the right hypochondrium, hypogastrium, biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like pathways. The rightmost labels also make clear that `No Match` remained common, consistent with a deliberately conservative rule-based Rome IV-informed mapping.

### S6. Short-term VAS direction prediction

**Table S3. Performance of Short-Term Direction Prediction Models**

| Model | Accuracy (mean +/- SD) | Balanced Accuracy | Macro F1 | Weighted F1 |
|:--|:--|:--|:--|:--|
| Majority | 0.717 +/- 0.016 | 0.500 +/- 0.000 | 0.418 +/- 0.005 | 0.599 +/- 0.021 |
| Persistence-direction | 0.579 +/- 0.032 | 0.531 +/- 0.025 | 0.523 +/- 0.025 | 0.594 +/- 0.031 |
| Logistic regression | 0.659 +/- 0.011 | 0.654 +/- 0.016 | 0.626 +/- 0.012 | 0.674 +/- 0.010 |

Abbreviations: SD, standard deviation; F1, harmonic mean of precision and recall; Macro F1, unweighted mean of class-specific F1 scores; Weighted F1, support-weighted mean of class-specific F1 scores. The persistence-direction model predicts decrease when the current local slope is sufficiently negative and otherwise predicts non-decrease.

The logistic model's improvement in balanced accuracy reflects better discrimination across both classes, not a simple tendency to predict the majority state. Table S3 is retained here because it provides the full metric breakdown that is summarized graphically in the main manuscript.

### S7. Complementary classifier diagnostics

**Figure S5. Complementary Phenotype-Classification Random Forest Feature Importance.**

![Figure S5. Complementary Phenotype-Classification Random Forest Feature Importance.](data/figures/figure15_ecg_feature_importance.png)

*Caption:* Random forest feature importance values from the complementary baseline-plus-physiology phenotype-classification analysis. Abbreviations: CCEI, Chronic Capsaicin Exposure Index; AES, Acute Exposure Score; ECG, electrocardiographic; EGG, electrogastrographic; HR, heart rate; SQI, signal quality index.

The highest-ranked variables included CCEI, spicy food preference, AES, usual spiciness level, time since last spicy intake, spicy food frequency, ECG artifact ratio, ECG-EGG coherence mean, EGG signal quality, and heart rate-EGG correlation.

The ranked variables identify predictors that contributed within this fitted model family. The importance profile remains model-specific and does not imply that these variables are stable standalone markers of phenotype membership across datasets or modeling choices.

### S8. Safety

**Table S4. Summary of Adverse Events**

| Safety outcome | Number of participants | Percentage |
|:--|--:|:--|
| Any adverse event | 9 | 4.2% |
| Serious adverse event | 0 | 0.0% |
| Medical intervention required | 0 | 0.0% |
| Protocol discontinuation due to adverse event | 9 | 4.2% |
| Hospitalization | 0 | 0.0% |

Nine participants (4.2%) experienced T-coded adverse events that ended the trial early. No serious adverse events occurred, no medical intervention or hospitalization was required, and all symptoms resolved within 30 minutes.

### S9. Short supplementary interpretation

The retained supplementary materials focus on analyses that extend the main-text composite figures rather than duplicate them. Figures S1 and S2 show that age and standardized physiology features contained some between-phenotype structure, but not enough to recover temporal phenotypes with high accuracy from baseline information alone.

Figure S3 adds local temporal motifs that help explain why DTW-based clustering separated the phenotypes even when trajectories overlapped at some absolute intensity levels. Tables S1-S2 and Figure S4 extend the symptom-pattern interpretation by showing that recurrent symptom-region hubs and phenotype-to-symptom-region-Rome IV flows remained concentrated rather than diffuse across the cohort.

Table S3, Figure S5, and Table S4 define the practical limits of interpretation around short-horizon forecasting, feature attribution, and safety. Together, the appendix supports the main manuscript without repeating figures that are already shown directly in the composite main-text panels.
