# Supplementary Appendix

**Supplementary Material for:** "Temporal Dynamics and Phenotypic Heterogeneity in Oral Capsaicin-Induced Human Visceral Pain"

This appendix provides expanded methods, interpretation of the supplementary figures and tables, and supporting reporting material for the intervention and observational design. The main manuscript presents three composite figures; this appendix retains the standalone panels and supporting outputs for readers who want the underlying detail.

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

The primary model set included class-balanced logistic regression, class-balanced random forest, gradient boosting, histogram-based gradient boosting, multilayer perceptron with early stopping, and a stacking ensemble. Stratified ten-fold cross-validation estimated model performance, with balanced accuracy and macro F1 as the primary metrics. A complementary classifier family used the same encoded matrix to generate the feature-importance and confusion-matrix summaries shown in Figures 15 and 16.

These analyses tested whether pre-exposure trait-like information could predict temporal phenotype membership without the evolving pain trajectory. The feature matrix is a heterogeneous baseline descriptor set, not a mechanistically unified biomarker panel. The supplementary feature-importance outputs rank variables that contributed within the fitted models; they do not identify stable causal determinants of phenotype membership.

## Supplementary Results

Figures 4-16 expand analyses summarized in main-text Figures 1-3.

### S3. Early-window temporal phenotype classification

**Figure 4. Early VAS window phenotype classification.**

![Figure 4. Early VAS window phenotype classification.](data/figures/figure5_early_window_classification.png)

*Caption:* Subject-level temporal phenotype classification performance as progressively longer early VAS windows are included. Abbreviation: VAS, visual analog scale.

Classification performance increased with longer early VAS windows. The best-performing model at 0 minutes was ExtraTrees, with accuracy 0.615 and balanced accuracy 0.632. At 3 minutes, histogram-based gradient boosting reached accuracy 0.726 and balanced accuracy 0.722. At 5 minutes, ExtraTrees reached accuracy 0.792 and balanced accuracy 0.790. At 8 minutes, sparse logistic regression reached accuracy 0.828 and balanced accuracy 0.821. At 20 minutes, sparse logistic regression reached accuracy 0.902 and balanced accuracy 0.897.

Performance improved stepwise as the window length increased, indicating that phenotype-relevant structure emerged early and strengthened over time. The three temporal phenotypes began to separate within the first few minutes after capsaicin exposure, before the full 20-minute series was complete.

### S4. Expanded baseline-plus-physiology phenotype summaries

**Figure 5. Baseline/Physiology Phenotype Prediction.**

![Figure 5. Baseline/Physiology Phenotype Prediction.](data/figures/figure6_baseline_prediction_performance.png)

*Caption:* Cross-validated performance of models predicting temporal phenotype membership from baseline demographic and questionnaire-derived exposure-history and symptom features, together with ECG, EGG, and ECG-EGG coupling features. Abbreviations: ECG, electrocardiographic; EGG, electrogastrographic; MLP, multilayer perceptron.

Across the primary model set, histogram-based gradient boosting achieved the highest mean accuracy (0.601 +/- 0.126), whereas random forest achieved the highest mean balanced accuracy (0.610 +/- 0.083). Logistic regression reached accuracy 0.527 and balanced accuracy 0.544. Multilayer perceptron showed the lowest performance.

Pre-exposure demographic, behavioral, and physiological descriptors captured only modest between-phenotype signal. The evolving VAS trajectory in Figure 4 contained more phenotype-specific information than the baseline feature matrix.

**Figure 6. Age by Phenotype.**

![Figure 6. Age by Phenotype.](data/figures/figure7_age_by_phenotype.png)

*Caption:* Age distributions stratified by temporal phenotype.

Age distributions overlapped across delayed-peak, early-sustained, and late-rising phenotypes.

This matched the broader baseline-prediction result: age alone did not organize the time-based phenotypes identified here.

**Figure 7. Standardized ECG/EGG Feature Distributions.**

![Figure 7. Standardized ECG/EGG Feature Distributions.](data/figures/figure8_ecg_egg_features.png)

*Caption:* Standardized ECG and EGG feature distributions across temporal phenotypes. Abbreviations: ECG, electrocardiographic; EGG, electrogastrographic; HR, heart rate; SDNN, standard deviation of normal-to-normal intervals; LF/HF, low-frequency/high-frequency power ratio.

Feature distributions showed partial between-cluster differences with substantial overlap.

Visual separation in a subset of features did not translate into strong multivariable phenotype classification, indicating that the available physiological feature set was insufficient to recover the temporal phenotypes with high accuracy.

### S5. Onset timing, survival curves, and local temporal motifs

**Figure 8. Onset and change-point timing.**

![Figure 8. Onset and change-point timing.](data/figures/figure9_onset_timing.png)

*Caption:* Threshold-defined onset, derivative-defined onset, and PELT-derived change-point timing for individual VAS trajectories after capsaicin administration. Abbreviations: VAS, visual analog scale; PELT, pruned exact linear time.

Most PELT change points occurred at minute 5 (164 participants), with smaller concentrations at minutes 10 (41 participants) and 15 (3 participants).

The concentration around minute 5 gives a concrete anchor for a common early transition from rise to stabilization or decline. It also supports trajectory-oriented analyses, because the timing structure was not uniformly distributed across the observation window.

**Figure 9. Kaplan-Meier event curves for onset and relief.**

![Figure 9. Kaplan-Meier event curves for onset and relief.](data/figures/figure10_survival_curves.png)

*Caption:* Kaplan-Meier curves for time to pain onset and time to pain relief after oral capsaicin administration.

Median onset occurred at 1.0 minute. Median relief was not reached within follow-up because only 12 of 216 participants met the relief criterion.

Rapid onset and incompletely observed relief suggest that the upward and downward phases should not be treated as mirror images. Onset was concentrated early, whereas recovery extended beyond the follow-up window for most participants.

**Figure 10. Cluster-specific shapelets.**

![Figure 10. Cluster-specific shapelets.](data/figures/figure11_shapelets.png)

*Caption:* Sub-figures are arranged by phenotype in rows and by shapelet rank in columns. Each panel shows one cluster-discriminative shapelet illustrating a local temporal motif for the delayed-peak, early-sustained, or late-rising phenotype. The solid line marks the highlighted shapelet, the dashed line shows the full source trajectory, and the shaded region marks the post-capsaicin time window spanned by the shapelet. AUC denotes the one-vs-rest area under the receiver operating characteristic curve, `d` denotes Cohen's d effect size, and `t` denotes the post-capsaicin time window in minutes.

Delayed-peak responders showed motifs with deferred maxima followed by decline, early-sustained responders showed plateau-like motifs, and late-rising responders showed gradual upward fragments.

These local motifs help explain why DTW-based clustering separated the phenotypes even when full-length trajectories overlapped in absolute intensity at some time points. Discriminative information was partly embedded in short contiguous subsequences, beyond global peak value or total pain burden.

### S6. Symptom-region and Rome IV-informed supplementary visualizations

**Figure 11. Symptom-region co-occurrence heatmap.**

![Figure 11. Symptom-region co-occurrence heatmap.](data/figures/figure12_symptom_region_heatmap.png)

*Caption:* Participant-level co-occurrence counts between reported symptom categories and anatomical regions after capsaicin administration.

The largest co-occurrence counts were concentrated in the right hypochondrium and hypogastrium, particularly for abdominal distension, nausea, and abdominal pain.

The visualization distinguishes recurrent symptom-region combinations from isolated reports. It shows which symptom-region pairings dominated the cohort-level experiential profile, not which anatomical site generated the sensation.

**Figure 12. Symptom-Rome IV co-occurrence heatmap.**

![Figure 12. Symptom-Rome IV co-occurrence heatmap.](data/figures/figure13_symptom_rome_heatmap.png)

*Caption:* Associations between reported symptom categories and Rome IV-informed symptom-pattern alignments generated by the rule-based mapping framework. Abbreviations: CNVS, chronic nausea and vomiting syndrome; FABD-like, functional abdominal bloating/distension-like; FC/DD-like, functional constipation/defecatory disorder-like; FD-PDS-like, postprandial distress syndrome-like functional dyspepsia; IBS-like, irritable bowel syndrome-like; Unspecified FGI, unspecified functional gastrointestinal symptom pattern.

Abdominal distension and abdominal pain contributed across biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like alignments.

Because the Rome IV-informed mapping was symptom-based and rule-driven, this heatmap represents overlap in phenomenology rather than diagnostic adjudication. Several symptom categories contributed across multiple construct-aligned profiles instead of mapping one-to-one onto a single category.

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

**Figure 13. Temporal phenotype to symptom-region-Rome IV flow structure.**

![Figure 13. Sankey diagram linking temporal phenotype, symptom burden, perceived region, and Rome IV-informed pattern.](data/figures/figure14_network_sankey.png)

*Caption:* Flow widths represent participant-level symptom-region co-occurrence counts expanded within each temporal phenotype and linked to the participant's top Rome IV-informed category. To preserve readability, lower-frequency symptoms, regions, and Rome-pattern categories were grouped into `Other` nodes. Rome-pattern labels report participant-level `n (%)` together with flow counts. Label abbreviations: `Abd Pain`, abdominal pain; `R-Hypo`, right hypochondrium; `Hypo`, hypogastrium; `L-Hypo`, left hypochondrium; `R-Lumb`, right lumbar. `No Match` indicates that no Rome IV-informed category was assigned by the rule-based mapping.

The Sankey view emphasizes that the three temporal phenotypes did not differ only in trajectory shape. All phenotypes fed strongly into abdominal distension, nausea, and abdominal pain, but the downstream region and Rome-pattern distributions remained concentrated around the right hypochondrium, hypogastrium, biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like pathways. The rightmost labels also make clear that `No Match` remained common, consistent with a deliberately conservative rule-based Rome IV-informed mapping.

### S7. Short-term VAS direction prediction

**Figure 14. Short-term VAS direction classification performance.**

![Figure 14. Short-term VAS direction classification performance.](data/figures/figure14_direction_classification.png)

*Caption:* Performance for short-term prediction of whether the next VAS value would decrease, comparing majority, persistence-direction, and logistic regression models. Abbreviations: VAS, visual analog scale; Macro F1, unweighted mean of class-specific F1 scores.

Logistic regression achieved the highest balanced accuracy (0.654 +/- 0.016) and macro F1 (0.626 +/- 0.012). The majority classifier yielded higher raw accuracy because of class imbalance but remained at balanced accuracy 0.500. The persistence-direction model showed intermediate performance.

The divergence between raw accuracy and balanced accuracy reflects the imbalance in direction labels. The logistic model's improvement in balanced accuracy reflects better discrimination across both classes, not a simple tendency to predict the majority state.

**Table S3. Performance of Short-Term Direction Prediction Models**

| Model | Accuracy (mean +/- SD) | Balanced Accuracy | Macro F1 | Weighted F1 |
|:--|:--|:--|:--|:--|
| Majority | 0.717 +/- 0.016 | 0.500 +/- 0.000 | 0.418 +/- 0.005 | 0.599 +/- 0.021 |
| Persistence-direction | 0.579 +/- 0.032 | 0.531 +/- 0.025 | 0.523 +/- 0.025 | 0.594 +/- 0.031 |
| Logistic regression | 0.659 +/- 0.011 | 0.654 +/- 0.016 | 0.626 +/- 0.012 | 0.674 +/- 0.010 |

Abbreviations: SD, standard deviation; F1, harmonic mean of precision and recall; Macro F1, unweighted mean of class-specific F1 scores; Weighted F1, support-weighted mean of class-specific F1 scores. The persistence-direction model predicts decrease when the current local slope is sufficiently negative and otherwise predicts non-decrease.

### S8. Complementary classifier diagnostics

**Figure 15. Complementary Phenotype-Classification Random Forest Feature Importance.**

![Figure 15. Complementary Phenotype-Classification Random Forest Feature Importance.](data/figures/figure15_ecg_feature_importance.png)

*Caption:* Random forest feature importance values from the complementary baseline-plus-physiology phenotype-classification analysis. Abbreviations: CCEI, Chronic Capsaicin Exposure Index; AES, Acute Exposure Score; ECG, electrocardiographic; EGG, electrogastrographic; HR, heart rate; SQI, signal quality index.

The highest-ranked variables included CCEI, spicy food preference, AES, usual spiciness level, time since last spicy intake, spicy food frequency, ECG artifact ratio, ECG-EGG coherence mean, EGG signal quality, and heart rate-EGG correlation.

The ranked variables identify predictors that contributed within this fitted model family. The importance profile remains model-specific and does not imply that these variables are stable standalone markers of phenotype membership across datasets or modeling choices.

**Figure 16. Complementary Phenotype-Classification Confusion Matrix.**

![Figure 16. Complementary Phenotype-Classification Confusion Matrix.](data/figures/figure16_ecg_confusion_matrix.png)

*Caption:* Out-of-fold temporal phenotype predictions from the best-performing complementary baseline-plus-physiology classifier (random forest).

The confusion matrix showed partial separation across the three temporal phenotypes, with overlap between neighboring response patterns. That pattern fits recurring temporal responses along a continuum more than rigidly separated classes.

### S9. Safety

**Table S4. Summary of Adverse Events**

| Safety outcome | Number of participants | Percentage |
|:--|--:|:--|
| Any adverse event | 9 | 4.2% |
| Serious adverse event | 0 | 0.0% |
| Medical intervention required | 0 | 0.0% |
| Protocol discontinuation due to adverse event | 9 | 4.2% |
| Hospitalization | 0 | 0.0% |

Nine participants (4.2%) experienced T-coded adverse events that ended the trial early. No serious adverse events occurred, no medical intervention or hospitalization was required, and all symptoms resolved within 30 minutes.

## Supplementary Discussion

### S10. Interpretation of supplementary analyses

The supplementary analyses narrow the main interpretation. The observed heterogeneity was temporal and structured, but baseline descriptors captured only part of it. In Figure 4, classification improved as short post-capsaicin VAS prefixes were added, indicating that phenotype-relevant information became visible early in the response, before the complete 20-minute trajectory was available. The delayed-peak, early-sustained, and late-rising patterns did not emerge only from end-of-window summaries; they began to diverge within the early post-exposure interval, consistent with broader pain-literature interest in temporal dynamics as a distinct analytic domain rather than a by-product of static intensity measurement [26,27].

The timing analyses clarify that early divergence does not imply a single uniform transition point for every participant. Figure 8 shows a strong concentration of PELT-derived change points around minute 5, but not an exclusive transition at that minute. Figure 9 shows rapid onset and incompletely observed relief during follow-up. Together, these results support an asymmetric view of the pain trajectory: the ascending phase was concentrated early, whereas the descending phase was slower, more heterogeneous, and often incomplete within the observation window. That asymmetry is consistent with prior experimental and mechanistic work on capsaicin and TRPV1 signaling, which suggests that visceral responses are shaped by initial receptor activation as well as downstream modulation, sensitization, and desensitization over time [12,15-18,20-22].

Across Figures 4, 8, 9, and 10, the protocol yielded convergent temporal structure: early informative prefixes, a concentrated transition zone around minute 5, and recoverable local motifs and phenotype assignments. Within the present standardized protocol, these features support operational controllability and reproducible cohort-level temporal organization, even though between-session trait stability still requires direct testing.

Figure 10 adds a local view of the trajectory signal. Each panel places the highlighted shapelet inside its underlying trajectory, showing that similar absolute intensities can belong to different temporal contexts: a value of moderate intensity may represent a rising segment in one phenotype, a plateau in another, or a declining segment in a third. That distinction explains why shape-based methods such as DTW and shapelets are useful for trajectory phenotyping [33-36]. In the present dataset, delayed-peak motifs had deferred maxima followed by decline, early-sustained motifs had relatively flat or slowly resolving plateaus, and late-rising motifs had upward fragments appearing later in the observation period. The supplementary figure helps explain how the clustering retained temporal organization even when trajectories overlapped at individual time points.

Figures 5, 6, 7, 15, and 16 suggest that baseline demographic, exposure-history, symptom, ECG, EGG, and ECG-EGG coupling variables contained some between-phenotype structure, but not enough for high-accuracy phenotype recovery. Age distributions overlapped, standardized physiology features showed partial visual separation, and complementary classifier diagnostics showed incomplete class discrimination. The temporal phenotypes recurred within this dataset, but the available pre-exposure feature set did not predict phenotype membership with high accuracy. The baseline matrix captured some trait-like variability, but not enough to serve as a stable biomarker panel for phenotype assignment.

The symptom-region and Rome IV-informed analyses extend the interpretation from time-course structure to symptom pattern and perceived location. Figures 11, 12, and 13, together with Tables S1 and S2, show that the cohort-level experience was not spatially or symptomatically diffuse. Repeated pairings centered on the right hypochondrium and hypogastrium, and several symptom categories contributed across biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like alignments. Figure 13 further shows that these alignments were reached through overlapping phenotype-to-symptom-region flows rather than fully segregated phenotype-specific branches. These pairings indicate that oral capsaicin evokes more than a unitary "pain intensity" response. It produces recurring combinations of discomfort, distension, nausea, and regionally perceived sensations that overlap with clinically recognized symptom constructs at the level of phenomenology [7,8,10,11,24,25,31].

The network summaries also help distinguish prevalence from structural prominence. A symptom can be frequent yet analytically limited if it remains tied to one region, whereas a hub-like symptom or region participates in many pairings and helps organize the broader co-occurrence pattern. Figure 13 adds a phenotype-aware flow view by showing that the main temporal clusters converge onto overlapping symptom-region hubs rather than separate symptom repertoires. It also shows that the terminal Rome-pattern layer was dominated by a small number of common outputs plus a substantial `No Match` remainder. In the present data, the leading nodes were both common and structurally central. That pattern suggests that the induced experience was not assembled from random symptom lists but from recurring symptom-region configurations that reappeared across participants. For future experimental phenotyping, this view helps identify which perceptual elements may be most informative beyond scalar VAS endpoints.

The network results should remain descriptive. This construction expanded participant-level symptom-region combinations into cohort-level co-occurrence counts, so it highlights recurrence and concentration rather than causal pathways or organ-specific generators. The Rome IV-informed layer adds construct-level context by showing which symptom sets overlapped with clinically recognized patterns, but it does not convert an acute provocation model into a diagnostic framework. Together, these analyses clarify the symptom pattern without overextending claims about mechanism, anatomical inference, or FGID classification.

Figure 14 and Table S3 address a narrower question about temporal organization. This task did not predict phenotype membership or overall response burden; it asked whether recent trajectory history could predict the next minute-to-minute direction of VAS change. Logistic regression showed moderate performance, suggesting that local trajectory state contained information about immediate future movement. This result is consistent with the broader trajectory findings and indicates local temporal dependencies even when longer-term recovery remains heterogeneous.

For future intervention studies, that predictive signal is practically important: it suggests that the evolving post-capsaicin trajectory contains enough short-horizon information to support prospective forecasting frameworks. The current dataset does not estimate intervention-related improvement directly, but it provides a defensible methodological starting point for models that target treatment-associated change once interventional data are collected.

The safety summary matters because censoring affects what the time-course methods estimate. T-coded trial terminations were treated as adverse events, and once an `E` or `T` marker appeared, subsequent VAS values were censored in the early-window analyses. This rule preserves the temporal integrity of the observed data rather than imputing unobserved post-termination values. All T-coded events resolved within 30 minutes, and no serious adverse events occurred, supporting the tolerability of the model within the monitored setting. A small subgroup did not complete the full protocol. The reported trajectory structure therefore reflects both between-participant heterogeneity and the operating boundary imposed by symptom tolerance. Future studies should make that boundary explicit when comparing window lengths, defining relief, or handling incomplete follow-up.

Across the appendix, early-window classification, change-point timing, survival structure, DTW-based clustering, and local shapelets all support the temporal phenotypes. Symptom-region, Sankey, and Rome IV-informed analyses add symptom quality, perceived region, and construct-level flow structure, whereas classifier diagnostics and safety summaries define the limits of interpretation. Together, these analyses support the oral capsaicin paradigm as a controllable experimental platform with coherent temporal organization and usable short-horizon predictive signal, while preserving clear boundaries around diagnosis, mechanism, longitudinal stability, and treatment-response prediction [3,4,7,8,26,27,29,30,37].
