# Supplementary Appendix

**Supplementary Material for:** "Temporal Dynamics and Phenotypic Heterogeneity in Oral Capsaicin-Induced Human Visceral Pain"

This appendix expands the methodological detail, provides figure-by-figure and table-by-table interpretation for the supplementary outputs, and documents reporting materials that support transparent description of the intervention and observational design. The intent is to complement the main manuscript rather than repeat it verbatim: the main paper emphasizes the core narrative, whereas this appendix preserves analytic detail, auxiliary visualizations, and reporting artifacts that are helpful for reviewers and replication.

Citation numbers in this appendix follow the main manuscript reference list.

## Supplementary Methods

### S1. Early-window temporal phenotype classification

Early-window classification was formulated as a subject-level phenotype-prediction task. The baseline-only dataset used the same baseline demographic and questionnaire-derived exposure-history and symptom features, together with electrocardiographic (ECG), electrogastrographic (EGG), and ECG-EGG coupling features, as the main phenotype-prediction analysis. Additional datasets appended the first 3, 5, 8, or 20 minutes of post-capsaicin VAS data.

For each early window, retained predictors included the raw minute-level VAS values and derived summary variables: mean, minimum, maximum, last value, prefix area under the curve, range, linear slope, early delta, and within-prefix peak time. Values marked `E` or `T` were treated as censored; once either marker appeared, all subsequent VAS values for that participant were set to missing before feature extraction.

Candidate classifiers included sparse logistic regression, standard logistic regression, radial and linear support vector machines, ridge classification, k-nearest neighbors, random forest, extra trees, histogram-based gradient boosting, and Gaussian naive Bayes. Performance was evaluated with stratified ten-fold cross-validation. Accuracy, balanced accuracy, macro F1, and weighted F1 were calculated from out-of-fold predictions.

This design was intentionally prefix-based. At each evaluation horizon, only information available up to that time point was used, so the task assessed how quickly phenotype-relevant trajectory structure emerged rather than how well full-trajectory summaries could be reconstructed retrospectively. The resulting comparison therefore addresses a practically important question: when does the observed signal become sufficiently informative to distinguish delayed-peak, early-sustained, and late-rising response patterns?

### S2. Expanded baseline-plus-physiology phenotype prediction

The baseline phenotype-prediction matrix contained demographic variables, questionnaire-derived exposure-history and symptom variables, ECG features, EGG features, and ECG-EGG coupling features. Questionnaire-derived variables included age, sex, body mass index, height, weight, alcohol consumption, spicy food frequency, usual spiciness level, spicy food preference, maximum tolerable spiciness, Chronic Capsaicin Exposure Index (CCEI), Acute Exposure Score (AES), recent spicy food intake, time since last spicy intake, spicy episodes in the previous 24 hours, baseline gastrointestinal symptom burden, and time since last meal.

ECG-derived variables included heart-rate-variability and signal-quality measures. EGG-derived variables included dominant frequency, power, rhythm-band proportions, entropy, flatness, instability, and signal-quality indices. ECG-EGG coupling variables included cross-correlation, lag, coherence, energy ratio, and heart rate-EGG correlation summaries. Missing values were imputed with column medians.

The primary model set included class-balanced logistic regression, class-balanced random forest, gradient boosting, histogram-based gradient boosting, multilayer perceptron with early stopping, and a stacking ensemble. Stratified ten-fold cross-validation was used. Balanced accuracy and macro F1 were treated as the primary performance metrics. A complementary classifier family using the same encoded matrix generated the feature-importance and confusion-matrix summaries shown in Figures 15 and 16.

These analyses were designed to test whether temporal phenotype membership could be inferred from pre-exposure trait-like information rather than from the evolving pain trajectory itself. Accordingly, this feature matrix should be interpreted as a heterogeneous baseline descriptor set, not as a mechanistically unified biomarker panel. The supplementary feature-importance outputs are therefore useful for ranking the variables that contributed most within the fitted models, but they should not be overinterpreted as evidence of stable causal determinants of phenotype membership.

## Supplementary Results

### S3. Early-window temporal phenotype classification

**Figure 5. Early VAS window phenotype classification.**

![Figure 5. Early VAS window phenotype classification.](data/figures/figure5_early_window_classification.png)

*Legend:* Subject-level temporal phenotype classification performance as progressively longer early VAS windows are included.

Classification performance increased with longer early VAS windows. The best-performing model at 0 minutes was ExtraTrees, with accuracy 0.615 and balanced accuracy 0.632. At 3 minutes, histogram-based gradient boosting reached accuracy 0.726 and balanced accuracy 0.722. At 5 minutes, ExtraTrees reached accuracy 0.792 and balanced accuracy 0.790. At 8 minutes, sparse logistic regression reached accuracy 0.828 and balanced accuracy 0.821. At 20 minutes, sparse logistic regression reached accuracy 0.902 and balanced accuracy 0.897.

The monotonic performance gain across progressively longer windows supports the interpretation that phenotype-relevant structure emerges early and strengthens over time. In other words, the three temporal phenotypes are not visible only after the full 20-minute series is complete; they begin to separate within the first few minutes after capsaicin exposure.

### S4. Expanded baseline-plus-physiology phenotype summaries

**Figure 6. Baseline and physiological phenotype prediction.**

![Figure 6. Baseline and physiological phenotype prediction.](data/figures/figure6_baseline_prediction_performance.png)

*Legend:* Cross-validated performance of models predicting temporal phenotype membership from baseline demographic and questionnaire-derived exposure-history and symptom features, together with ECG, EGG, and ECG-EGG coupling features.

Across the primary model set, histogram-based gradient boosting achieved the highest mean accuracy (0.601 +/- 0.126), whereas random forest achieved the highest mean balanced accuracy (0.610 +/- 0.083). Logistic regression reached accuracy 0.527 and balanced accuracy 0.544. Multilayer perceptron showed the lowest performance.

These results indicate that pre-exposure demographic, behavioral, and physiological descriptors captured only modest between-phenotype signal. The contrast with Figure 5 is informative: the evolving VAS trajectory itself contained substantially more phenotype-specific information than the baseline feature matrix.

**Figure 7. Age distribution by temporal phenotype.**

![Figure 7. Age distribution by temporal phenotype.](data/figures/figure7_age_by_phenotype.png)

*Legend:* Age distributions stratified by temporal phenotype.

Age distributions overlapped across delayed-peak, early-sustained, and late-rising phenotypes.

This overlap is consistent with the broader baseline-prediction results and argues against age alone serving as a dominant organizing variable for the time-based phenotypes identified here.

**Figure 8. Standardized ECG/EGG feature distributions.**

![Figure 8. Standardized ECG/EGG feature distributions.](data/figures/figure8_ecg_egg_features.png)

*Legend:* Standardized ECG and EGG feature distributions across temporal phenotypes.

Feature distributions showed partial between-cluster differences with substantial overlap.

The overlap is important for interpretation. Visual separation in a subset of features does not translate into strong phenotype classification at the multivariable level, reinforcing the conclusion that the currently available physiological feature set was insufficient to recover the temporal phenotypes with high accuracy.

### S5. Onset timing, survival curves, and local temporal motifs

**Figure 9. Onset and change-point timing.**

![Figure 9. Onset and change-point timing.](data/figures/figure9_onset_timing.png)

*Legend:* Threshold-defined onset, derivative-defined onset, and PELT-derived change-point timing for individual VAS trajectories after capsaicin administration.

Most PELT change points occurred at minute 5 (164 participants), with smaller concentrations at minutes 10 (41 participants) and 15 (3 participants).

This concentration around minute 5 provides an empirical anchor for the visual impression of a common early transition from rise to stabilization or decline. It also supports the use of trajectory-oriented analyses, because the timing structure is not uniformly distributed across the observation window.

**Figure 10. Kaplan-Meier event curves for onset and relief.**

![Figure 10. Kaplan-Meier event curves for onset and relief.](data/figures/figure10_survival_curves.png)

*Legend:* Kaplan-Meier curves for time to pain onset and time to pain relief after oral capsaicin administration.

Median onset occurred at 1.0 minute. Median relief was not reached within follow-up because only 12 of 216 participants met the relief criterion.

The asymmetry between rapid onset and incompletely observed relief is one of the clearest indications that upward and downward phases should not be treated as mirror images. The onset process was concentrated early, whereas recovery extended beyond the follow-up window for most participants.

**Figure 11. Cluster-specific shapelets.**

![Figure 11. Cluster-specific shapelets.](data/figures/figure11_shapelets.png)

*Legend:* Sub-figures are arranged by phenotype in rows and by shapelet rank in columns. Each panel shows one cluster-discriminative shapelet illustrating a local temporal motif for the delayed-peak, early-sustained, or late-rising phenotype.

Delayed-peak responders showed motifs with deferred maxima followed by decline, early-sustained responders showed plateau-like motifs, and late-rising responders showed gradual upward fragments.

These local motifs help explain why DTW-based clustering separated the phenotypes even when full-length trajectories overlapped in absolute intensity at some time points. The discriminative information was partly embedded in short contiguous subsequences rather than only in the global peak value or total pain burden.

### S6. Symptom-region and Rome IV-informed supplementary visualizations

**Figure 12. Symptom-region co-occurrence heatmap.**

![Figure 12. Symptom-region co-occurrence heatmap.](data/figures/figure12_symptom_region_heatmap.png)

*Legend:* Participant-level co-occurrence counts between reported symptom categories and anatomical regions after capsaicin administration.

The largest co-occurrence counts were concentrated in the right hypochondrium and hypogastrium, particularly for abdominal distension, nausea, and abdominal pain.

This visualization helps distinguish recurrent symptom-region combinations from isolated reports. Its value is descriptive and structural: it shows which symptom-region pairings dominate the cohort-level experiential profile, not which anatomical site generated the sensation.

**Figure 13. Symptom-Rome IV co-occurrence heatmap.**

![Figure 13. Symptom-Rome IV co-occurrence heatmap.](data/figures/figure13_symptom_rome_heatmap.png)

*Legend:* Associations between reported symptom categories and Rome IV-informed symptom-pattern alignments generated by the rule-based mapping framework.

Abdominal distension and abdominal pain contributed across biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like alignments.

Because the Rome IV-informed mapping was symptom-based and rule-driven, this heatmap should be interpreted as overlap in phenomenology rather than as diagnostic adjudication. The figure is most useful for showing that several symptom categories contributed across multiple construct-aligned profiles rather than mapping one-to-one onto a single category.

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

### S7. Short-term VAS direction prediction

**Figure 14. Short-term VAS direction classification performance.**

![Figure 14. Short-term VAS direction classification performance.](data/figures/figure14_direction_classification.png)

*Legend:* Performance for short-term prediction of whether the next VAS value would decrease, comparing majority, persistence-direction, and logistic regression models.

Logistic regression achieved the highest balanced accuracy (0.654 +/- 0.016) and macro F1 (0.626 +/- 0.012). The majority classifier yielded higher raw accuracy because of class imbalance but remained at balanced accuracy 0.500. The persistence-direction model showed intermediate performance.

The divergence between raw accuracy and balanced accuracy is especially relevant here because the direction labels were imbalanced. The logistic model's improvement in balanced accuracy therefore reflects better discrimination across both classes rather than a simple tendency to predict the majority state.

**Table S3. Performance of Short-Term Direction Prediction Models**

| Model | Accuracy (mean +/- SD) | Balanced Accuracy | Macro F1 | Weighted F1 |
|:--|:--|:--|:--|:--|
| Majority | 0.717 +/- 0.016 | 0.500 +/- 0.000 | 0.418 +/- 0.005 | 0.599 +/- 0.021 |
| PersistenceDir | 0.579 +/- 0.032 | 0.531 +/- 0.025 | 0.523 +/- 0.025 | 0.594 +/- 0.031 |
| Logistic | 0.659 +/- 0.011 | 0.654 +/- 0.016 | 0.626 +/- 0.012 | 0.674 +/- 0.010 |

### S8. Complementary classifier diagnostics

**Figure 15. Complementary phenotype-classification random forest feature importance.**

![Figure 15. Complementary phenotype-classification random forest feature importance.](data/figures/figure15_ecg_feature_importance.png)

*Legend:* Random forest feature importance values from the complementary baseline-plus-physiology phenotype-classification analysis.

The highest-ranked variables included CCEI, spicy food preference, AES, usual spiciness level, time since last spicy intake, spicy food frequency, ECG artifact ratio, ECG-EGG coherence mean, EGG signal quality, and heart rate-EGG correlation.

The ranked variables illustrate which predictors contributed most strongly within this fitted model family, but the importance profile should be treated as model-specific. It does not imply that these variables are stable standalone markers of phenotype membership across datasets or modeling choices.

**Figure 16. Complementary phenotype-classification confusion matrix.**

![Figure 16. Complementary phenotype-classification confusion matrix.](data/figures/figure16_ecg_confusion_matrix.png)

*Legend:* Out-of-fold temporal phenotype predictions from the best-performing complementary classifier (random forest).

The confusion matrix showed partial separation across the three temporal phenotypes.

Misclassification was not random in a purely visual sense; rather, the matrix suggests partial overlap between neighboring response patterns, which is consistent with the broader interpretation that the temporal phenotypes reflect recurring patterns along a continuum rather than rigidly separated classes.

### S9. Safety

**Table S4. Summary of Adverse Events**

| Safety outcome | Number of participants | Percentage |
|:--|--:|:--|
| Any adverse event | 9 | 4.2% |
| Serious adverse event | 0 | 0.0% |
| Medical intervention required | 0 | 0.0% |
| Protocol discontinuation due to adverse event | 9 | 4.2% |
| Hospitalization | 0 | 0.0% |

Nine participants (4.2%) experienced T-coded adverse events that ended the trial early. No serious adverse events occurred, no medical intervention or hospitalization was required, and all symptoms resolved within 30 minutes without progression to a more severe condition.

## Supplementary Discussion

### S10. Interpretation of supplementary analyses

The supplementary analyses sharpen the central interpretation of the study by showing that the observed heterogeneity is temporal, structured, and only partly recoverable from baseline descriptors. Figure 5 is especially important in this respect. Classification improved steadily as short post-capsaicin VAS prefixes were added, indicating that phenotype-relevant information became visible early in the response rather than appearing only when the complete 20-minute trajectory was available. This matters methodologically because it argues against a purely retrospective reading of the clusters. The delayed-peak, early-sustained, and late-rising patterns were not created only by end-of-window summaries; they began to diverge within the early post-exposure interval, consistent with broader pain-literature interest in temporal dynamics as a distinct analytic domain rather than a by-product of static intensity measurement [26,27].

The supplementary timing analyses further clarify that early divergence does not imply a single uniform transition point for every participant. Figure 9 shows a strong concentration of PELT-derived change points around minute 5, but not an exclusive change point at that minute. In parallel, Figure 10 shows that onset was rapid and relief was much less completely observed within follow-up. Taken together, these results support an asymmetric view of the pain trajectory: the ascending phase was concentrated early, whereas the descending phase was slower, more heterogeneous, and often incomplete within the observation window. That asymmetry is consistent with prior experimental and mechanistic work on capsaicin and TRPV1 signaling, which suggests that visceral responses are shaped not only by initial receptor activation but also by downstream modulation, sensitization, and desensitization processes over time [12,15-18,20-22].

Figure 11 adds a different kind of evidence by showing that discriminative information was embedded in local subsequences, not only in global summaries such as peak VAS or total AUC. The revised shapelet display makes this easier to interpret because each panel now places the highlighted shapelet inside its full underlying trajectory. This presentation shows that similar absolute intensities can belong to different temporal contexts: a value of moderate intensity may represent a rising segment in one phenotype, a plateau in another, or a declining segment in a third. That distinction is precisely why shape-based methods such as DTW and shapelets are useful for trajectory phenotyping [34,35,37]. In the present dataset, delayed-peak motifs were characterized by deferred maxima followed by decline, early-sustained motifs by relatively flat or slowly resolving plateaus, and late-rising motifs by upward fragments appearing later in the observation period. The supplementary figure therefore helps explain how the clustering retained meaningful temporal organization even when trajectories overlapped at individual time points.

The baseline-plus-physiology analyses are also more informative in the supplement than they may appear from the headline performance values alone. Figures 6, 7, 8, 15, and 16 jointly suggest that some between-phenotype structure was present in baseline demographic, exposure-history, symptom, ECG, EGG, and ECG-EGG coupling variables, but that this structure was diffuse and not sufficiently strong to yield high-confidence phenotype recovery. The age distributions overlapped substantially, the standardized physiology features showed only partial visual separation, and the complementary classifier diagnostics indicated partial but incomplete class discrimination. This pattern is useful because it separates two related but distinct propositions: first, temporal phenotypes are reproducible response patterns within this provocation model; second, their membership is not determined with high accuracy by the currently available pre-exposure feature set. That distinction helps keep the study's contribution appropriately bounded. The present baseline matrix can be viewed as a heterogeneous descriptor set that captures some trait-like variability, but it does not yet constitute a stable biomarker panel for phenotype assignment.

The supplementary symptom-region and Rome IV-informed analyses extend the interpretation from time-course structure to phenomenological structure. Figures 12 and 13, together with Tables S1 and S2, show that the cohort-level experience was not spatially or symptomatically diffuse in a random sense. Instead, repeated pairings centered on the right hypochondrium and hypogastrium, and several symptom categories contributed across biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like alignments. This pattern supports the view that oral capsaicin evokes more than a unitary "pain intensity" response. It produces structured constellations of discomfort, distension, nausea, and regionally perceived sensations that can overlap with clinically recognized symptom constructs at the level of phenomenology [7,8,10,11,24,25,31]. At the same time, the supplement helps draw the necessary boundary: these analyses do not provide anatomical localization, and the Rome IV-informed mapping does not establish formal FGID diagnoses. Their value lies in describing how symptoms co-occur and how experimental sensations approximate established symptom constructs, not in collapsing acute provocation data into clinical classification.

The short-term direction-prediction analysis in Figure 14 and Table S3 provides a further, narrower perspective on temporal organization. This task did not attempt to predict phenotype membership or overall response burden. Instead, it asked whether the next minute-to-minute direction of VAS change could be inferred from recent trajectory history. The moderate but non-trivial performance of logistic regression suggests that local trajectory state contained information about immediate future movement, especially when evaluated with balanced metrics that accounted for label imbalance. This result is conceptually consistent with the broader trajectory findings. If the response were dominated by noise or by a single monotonic pattern, short-horizon direction prediction would be much less informative. The supplementary analysis therefore supports the idea that local temporal dependencies are present even when longer-term recovery remains heterogeneous.

The safety summary is also important for interpreting the supplementary analyses because the handling of censored trajectories affects what the time-course methods are estimating. T-coded trial terminations were treated as adverse events, and once an `E` or `T` marker appeared, subsequent VAS values were censored in the early-window analyses. This rule preserves the temporal integrity of the observed data rather than imputing unobserved post-termination values. The fact that all T-coded events resolved within 30 minutes and no serious adverse events occurred supports the tolerability of the model within the monitored setting, while still acknowledging that a small subgroup did not complete the full protocol. Analytically, this means the reported trajectory structure reflects both biologic heterogeneity and the realistic operating boundary imposed by symptom tolerance. That boundary is worth making explicit because it informs how future studies should compare window lengths, define relief, and handle incomplete follow-up.

Taken together, the supplementary materials strengthen the main manuscript in three ways. First, they show that the temporal phenotypes are supported by multiple complementary views of the same data: early-window classification, change-point timing, survival structure, DTW-based clustering, and local shapelets. Second, they show that phenomenological heterogeneity extends beyond intensity to symptom quality and perceived region. Third, they make the study's limits more transparent by showing where overlap remains, where classification is only modest, and where interpretation should remain descriptive rather than mechanistic. In that sense, the supplement is not ancillary decoration; it is the part of the study that demonstrates analytic triangulation. For experimental visceral pain research, that triangulation may be particularly useful because it links dense symptom time-series analysis with clinically interpretable constructs while preserving clear boundaries around diagnosis, mechanism, and prediction [3,4,7,8,26,27,29,30,37].

### S11. Reporting checklists and intervention documentation

Two existing reporting documents in this project should be treated as companion supplementary files for submission packaging:

- `TIDieR-Checklist-latest.md`
- `STROBE_checklist-latest.md`

They add value, but they are usually most useful as standalone reporting attachments rather than being pasted verbatim into the narrative appendix. The TIDieR checklist documents the capsaicin intervention in a structured replication-oriented format, whereas the STROBE checklist maps the observational study report to the recommended reporting items. For journal submission, the cleanest approach is:

- Keep the present `supplementary_latest.md` as the narrative supplementary appendix.
- Submit the TIDieR checklist as a separate supplementary/reporting file.
- Submit the STROBE checklist as a separate supplementary/reporting file.
- Mention in the cover letter or submission metadata that both checklists are included as reporting supplements.

If the target journal requires a single consolidated supplementary PDF, these checklists can be appended after the narrative appendix. If the journal permits multiple supplementary files, keeping them separate will usually make the appendix easier to read and will preserve the checklists' function as reporting tools rather than narrative prose.
