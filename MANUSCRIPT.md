# Title Page

**Title:** Temporal Dynamics and Phenotypic Heterogeneity of Capsaicin-Induced Visceral Pain in Humans: A Multi-Dimensional Analysis

**Word Count:** Main text 11,128 words (excluding references); abstract 349 words

## Abstract

**Background:** Functional gastrointestinal disorders (FGIDs) affect a substantial proportion of the global population, yet pain assessments often rely on static summaries that do not capture temporal response dynamics. The oral capsaicin model provides a reproducible experimental paradigm for studying visceral pain, but analytical approaches that integrate temporal, spatial, and symptom-level information remain underdeveloped.

**Objectives:** This study developed and evaluated a multidimensional analytical framework for characterizing individual responses in the oral capsaicin-induced pain model, integrating temporal dynamics, symptom mapping, and Rome IV-informed clinical alignment.

**Methods:** Time-resolved subjective pain responses were recorded from 216 participants following oral capsaicin administration. Pain intensity was measured at 1-minute intervals using a visual analog scale (VAS) over a 20-minute observation period. Analytical methods included change point detection (Pruned Exact Linear Time [PELT] algorithm), survival analysis (Kaplan-Meier), time-series clustering (dynamic time warping [DTW]-based K-means and fuzzy c-medoids), shapelet analysis, co-occurrence network analysis, tripartite network integration with Rome IV categories, short-term predictive modeling, and phenotype prediction from baseline characteristics.

**Results:** Capsaicin exposure elicited a robust biphasic pain response with rapid onset (median 1.0 minute by threshold method) and gradual resolution (median 5.0 minutes by survival analysis). DTW-based clustering identified three temporal phenotypes: delayed-peak responders (n=77), early-sustained responders (n=77), and late-rising responders (n=62), with moderate separation (average silhouette score=0.318). Abdominal distension was the most frequent symptom (71.3%), and the right hypochondrium emerged as the dominant anatomical region (64.8%) and symptom–region hub (weighted degree=368). Rome IV-informed mapping identified biliary pain-like, functional abdominal bloating/distension-like, and IBS-like symptom patterns. Logistic regression achieved balanced accuracy of 0.711 (macro F1=0.687) for short-term VAS direction prediction, while baseline/physiology-based phenotype prediction remained modest (best accuracy=0.495).

**Conclusions:** The oral capsaicin model exhibits structured, multidimensional dynamics that can be characterized using temporal phenotyping and network modeling. The proposed framework links experimental pain responses with clinically recognizable symptom constructs and provides a basis for future validation studies in visceral pain phenotyping.

**Keywords:** capsaicin, visceral pain, functional gastrointestinal disorders, time-series clustering, dynamic time warping, network analysis, Rome IV, phenotyping

## 1. Introduction

Visceral pain is one of the most common and clinically significant symptoms encountered in gastroenterology and contributes substantially to healthcare burden and impaired quality of life [1,2]. Unlike somatic pain, visceral pain is characterized by diffuse localization, poor spatial discrimination, referred sensations, and prominent emotional and autonomic accompaniments [3,4,32,33]. These features make visceral nociception difficult to study with static or retrospective assessment methods that do not capture its dynamic, multiphase structure.

Among the experimental paradigms developed to investigate visceral nociception in humans, the oral capsaicin model has emerged as a particularly valuable tool. Capsaicin, the pungent constituent of chili peppers (*Capsicum* spp.), acts as a selective agonist of the transient receptor potential vanilloid 1 (TRPV1) channel, a polymodal nociceptor expressed on sensory nerve endings throughout the gastrointestinal tract [7,8,16]. Upon oral ingestion, capsaicin activates upper gastrointestinal afferent pathways and can elicit burning, cramping, and distension-like sensations that overlap with symptom profiles reported by patients with functional gastrointestinal disorders (FGIDs) [5,6,14,20].

The molecular pharmacology of TRPV1 provides a mechanistic framework for understanding both the initiation and resolution of capsaicin-induced pain. TRPV1 is a nonselective cation channel gated by noxious heat (>43°C), low pH, endovanilloids (e.g., anandamide), and exogenous vanilloids such as capsaicin [7,9]. Upon activation, TRPV1 mediates calcium influx into sensory neurons, triggering action potential propagation and neuropeptide release from peripheral terminals, a process associated with neurogenic inflammation [10,11]. Sustained or repeated TRPV1 activation can induce calcium-dependent desensitization, whereby the channel progressively reduces its responsiveness to subsequent stimuli [12,13]. This dual excitatory-desensitizing dynamic is thought to contribute to the characteristic temporal trajectory of capsaicin-induced pain: rapid onset followed by gradual resolution.

Several features distinguish the oral capsaicin model from other experimental visceral pain paradigms. Oral administration engages upper gastrointestinal sensory pathways under near-physiological conditions, whereas rectal balloon distension and transcutaneous electrical stimulation probe more restricted or less naturalistic sensory inputs [7,14]. The response unfolds over approximately 15–20 minutes, with rapid onset, peak intensity, and gradual desensitization that can be sampled minute by minute [7,17]. At experimental doses, oral capsaicin produces transient, self-limiting gastrointestinal discomfort without lasting tissue injury [18,19]. Because capsaicin acts through the well-characterized TRPV1 channel, the experimental response has a defined mechanistic anchor [9,12].

Despite these advantages, capsaicin studies often reduce pain trajectories to static endpoints such as peak VAS, mean VAS, or area under the curve (AUC), which discard information about temporal shape [7,21-24]. Standard visceral pain assessments also tend to capture symptom quality and anatomical location separately, limiting systematic analysis of their coupling [25-28]. In addition, experimental symptom profiles are rarely aligned with Rome IV constructs, and population-level mean curves can mask substantial inter-individual heterogeneity [29-31,42-44].

This study optimized data analysis methods for the oral capsaicin-induced pain model by characterizing individual responses across temporal, spatial, symptom, and baseline physiological dimensions. The specific aims were to identify temporal pain-response phenotypes using DTW-based clustering; quantify spatial–symptom structure using co-occurrence network analysis; map symptom profiles to Rome IV-informed FGID categories; assess short-term predictability of symptom dynamics; and evaluate whether temporal phenotypes could be predicted from pre-experiment demographic, questionnaire, ECG, and EGG characteristics.

## 2. Methods

Detailed methodological descriptions are provided in Section 5.

### 2.1 Ethical Considerations

This study was approved by the Institutional Review Board of [Institution Name] (Approval No: [XXXX]). All participants provided written informed consent prior to enrollment. The study was conducted in accordance with the Declaration of Helsinki.

### 2.2 Reporting Guidelines

This study was reported in accordance with the STROBE (Strengthening the Reporting of Observational Studies in Epidemiology) reporting guideline where applicable, with additional reporting elements from TIDieR (Template for Intervention Description and Replication) for the capsaicin administration procedure.

### 2.3 Study Design and Participants

This study employed an experimental observational design using an oral capsaicin-induced visceral pain model. A total of 216 participants were monitored continuously for 20 minutes following capsaicin administration. Pain intensity was recorded at 1-minute intervals using a visual analog scale (VAS).

### 2.4 Capsaicin Administration and Exposure Protocol

Food-grade capsaicin (purity 98%; CAS No. 404-86-4; Ruimao Biotechnology Co., Ltd., Xi'an, China) was dissolved in ethanol (96%, v/v; Spirytus Rektyfikowany, Polmos, Poland) to prepare a 1% (w/v) stock solution. For each administration, 10 μL of the solution (equivalent to 1 mg capsaicin) was encapsulated into a gastro-soluble gelatin capsule (gelatin; Xuanyu Plastic Products Factory, Taizhou, China). The capsule was administered orally under direct observation by trained research staff. Following administration, participants were monitored continuously for 20 minutes in a controlled laboratory environment. All participants completed the full capsaicin administration protocol without dose adjustments. Safety monitoring was performed throughout the experimental session, and adverse events were recorded when symptoms exceeded the expected transient response to capsaicin or required clinical intervention. No dose modifications were required during the study.

### 2.5 Data Preprocessing

Time-series preprocessing treated values marked "E" (early termination) and "T" (technical termination) as censored. Once an E or T marker appeared, all subsequent measurements for that participant were set to missing (NaN) and excluded from downstream analyses.

### 2.6 Pain Assessment

Pain onset was determined using threshold-based, derivative-based, and change point detection methods. Survival analysis employed Kaplan–Meier methods with log-rank tests. Total pain exposure was quantified using area under the curve (AUC).

### 2.7 Clustering Analysis

Time-series clustering was performed using DTW-based K-means with DTW barycentric averaging (DBA) centroids and DTW-based fuzzy c-medoids clustering. Cluster-specific temporal features were extracted using shapelet analysis.

### 2.8 Symptom Assessment

Participant-reported gastrointestinal symptoms were recorded using a predefined coding system (symptoms: A–L; regions: 1–9). A bipartite representation of symptom–region relationships was constructed at the participant level.

### 2.9 Clinical Mapping

Participant-level symptom profiles were mapped to FGID categories based on Rome IV criteria using a rule-based scoring framework. A tripartite network was constructed comprising symptoms, anatomical regions, and Rome IV-aligned FGID categories.

### 2.10 Predictive Modeling

A sliding-window classification framework (window size = 3) predicted whether VAS would decrease at the next time point. Three models were evaluated: (1) majority classifier, (2) persistence direction model, and (3) logistic regression with class balancing. Group-wise cross-validation prevented information leakage.

### 2.11 Phenotype Prediction from Baseline Features

To assess whether temporal pain phenotypes could be predicted from pre-experiment characteristics, we trained classifiers to predict cluster membership using baseline demographic, questionnaire, electrocardiogram (ECG), and electrogastrography (EGG) data. Because habitual spicy food exposure has been associated with gastrointestinal symptom reporting [15], dietary exposure variables were included in the baseline feature set. Features included age, sex, body mass index, alcohol consumption, spicy food habits (frequency, usual spiciness level, preference, maximum tolerance), Chronic Capsaicin Exposure Index (CCEI), Acute Exposure Score (AES), recent spicy food intake (24 h), baseline gastrointestinal symptoms, heart rate variability parameters (SDNN, RMSSD, pNN50, LF/HF ratio), EGG spectral features (dominant frequency, normogastria/bradygastria/tachygastria percentages, spectral entropy), and ECG–EGG coupling metrics (cross-correlation, coherence). Six classifiers were evaluated: logistic regression with class balancing, random forest, gradient boosting, histogram-based gradient boosting, a multi-layer perceptron with early stopping, and a stacking ensemble. Model performance was assessed using stratified ten-fold cross-validation with balanced accuracy and macro F1-score as primary metrics. Random forest feature importance and out-of-fold confusion matrices were used for model interpretation.

## 3. Results

Detailed results are provided in Section 6.

### 3.1 Participant Characteristics

A total of 216 participants were included in the final analysis. All participants completed the capsaicin administration protocol and contributed at least one valid VAS measurement. No adverse events or serious adverse events occurred during the study. The baseline characteristics are summarized in Table 1.

**Table 1. Baseline Characteristics of Study Participants (N = 216)**

| Characteristic                           | Value       |
|:-----------------------------------------|:------------|
| Age, years, mean ± SD                    | 20.4 ± 1.9  |
| Sex, n (%)                               |             |
| Female                                   | 125 (57.9%) |
| Male                                     | 91 (42.1%)  |
| Height, cm, mean ± SD                    | 167.2 ± 8.9 |
| Weight, kg, mean ± SD                    | 60.3 ± 12.0 |
| BMI, kg/m², mean ± SD                    | 21.4 ± 3.3  |
| Time since last meal, hours, mean ± SD   | 4.0 ± 1.9   |
| Alcohol consumption, n (%)               |             |
| Non-drinker                              | 116 (53.7%) |
| Occasional drinker                       | 83 (38.4%)  |
| Regular drinker                          | 17 (7.9%)   |
| Spicy food frequency, mean ± SD          | 2.3 ± 1.2   |
| Usual spiciness level, mean ± SD         | 2.8 ± 1.1   |
| Preference for spicy food, mean ± SD     | 3.2 ± 1.1   |
| Maximum tolerable spiciness, mean ± SD   | 3.3 ± 1.0   |
| CCEI, mean ± SD                          | 20.1 ± 14.8 |
| Recent spicy food intake (24h), mean ± SD | 0.6 ± 0.5   |
| Time since last intake, hours, mean ± SD | 9.7 ± 4.7   |
| Number of episodes (24h), mean ± SD      | 0.9 ± 1.1   |
| AES, mean ± SD                           | 5.3 ± 6.8   |
| Baseline GI symptoms, n (%)              |             |
| No symptoms                              | 148 (68.5%) |
| Mild symptoms                            | 56 (25.9%)  |
| Moderate symptoms                        | 12 (5.6%)   |

Abbreviations: SD, standard deviation; BMI, body mass index; GI, gastrointestinal; CCEI, Chronic Capsaicin Exposure Index; AES, Acute Exposure Score.

### 3.2 Temporal Dynamics of Pain Response

**Figure 1. Group mean VAS trajectory.**

![Figure 1. Group mean VAS trajectory.](data/figures/figure1_group_mean_vas.png)

*Caption:* The figure shows the group-level mean VAS trajectory during the 20-minute observation period after oral capsaicin administration, with uncertainty shown as SEM.

*Abbreviations:* SEM, standard error of the mean; VAS, visual analog scale.

**Figure 2. Temporal pain phenotype trajectories.**

![Figure 2. Temporal pain phenotype trajectories.](data/figures/figure2_phenotype_trajectories.png)

*Caption:* The figure shows mean VAS trajectories stratified by DTW-derived temporal phenotype, with uncertainty shown as SEM.

*Abbreviations:* DTW, dynamic time warping; SEM, standard error of the mean; VAS, visual analog scale.

The average VAS score increased sharply within the first 2–4 minutes, peaking at 4.22 at minute 4, then gradually declined while remaining above zero throughout the observation period. This trajectory reflects a biphasic pain response. Change-point and time-to-event analyses, presented in extended figures, showed median threshold-defined onset at 1.0 minute, median derivative-defined onset at 2.0 minutes, a modal PELT change point at minute 5, and median relief time of 5.0 minutes. The group-level AUC was 64.56, reflecting cumulative pain burden.

### 3.3 Clustering Analysis

DTW-based clustering identified three temporal patterns: Cluster 1/delayed-peak responders (n = 77) exhibited delayed peak followed by gradual decline; Cluster 2/early-sustained responders (n = 77) showed an early rise with sustained moderate intensity; Cluster 3/late-rising responders (n = 62) demonstrated gradual increase with late-phase elevation. Silhouette analysis for the three-cluster solution yielded an average score of 0.318, indicating moderate separation. Shapelet analysis, shown in Figure 11, identified cluster-specific local motifs that supported the interpretation of these phenotypes.

### 3.4 Symptom Distribution and Network Analysis

**Figure 3. Symptom burden.**

![Figure 3. Symptom burden.](data/figures/figure3_symptom_burden.png)

*Caption:* The figure shows the frequency of participant-reported gastrointestinal symptoms after capsaicin administration.

*Abbreviations:* GI, gastrointestinal.

**Figure 4. Pain region burden.**

![Figure 4. Pain region burden.](data/figures/figure4_region_burden.png)

*Caption:* The figure shows the frequency of anatomical regions where symptoms were reported.

*Abbreviations:* None.

Abdominal distension was the most frequently reported symptom (154/216, 71.3%), followed by nausea (85/216, 39.4%) and abdominal pain (84/216, 38.9%). Symptoms were predominantly localized to the right hypochondrium (140/216, 64.8%) and hypogastrium (92/216, 42.6%). Co-occurrence heatmaps are provided in Figures 12 and 13.

The overall symptom–region network revealed structured associations. The strongest edge was abdominal distension–right hypochondrium (weight = 110). The right hypochondrium exhibited the highest weighted degree (368), identifying it as the dominant regional hub, followed by the hypogastrium (weighted degree = 267). In Rome IV-informed mapping, biliary pain-like patterns were most common (57/216, 26.4%), followed by functional abdominal bloating/distension-like (35/216, 16.2%) and IBS-like patterns (25/216, 11.6%).

### 3.5 Short-Term Direction Prediction

**Figure 5. Early VAS window phenotype classification.**

![Figure 5. Early VAS window phenotype classification.](data/figures/figure5_early_window_classification.png)

*Caption:* The figure shows subject-level temporal phenotype classification accuracy as progressively longer early VAS windows are included.

*Abbreviations:* VAS, visual analog scale.

**Figure 6. Baseline and physiological phenotype prediction.**

![Figure 6. Baseline and physiological phenotype prediction.](data/figures/figure6_baseline_prediction_performance.png)

*Caption:* The figure shows cross-validated accuracy for models predicting temporal phenotype membership from baseline demographic, questionnaire, ECG, and EGG features.

*Abbreviations:* ECG, electrocardiogram; EGG, electrogastrography.

Temporal phenotype classification improved as more early VAS information was included. Classification using no post-capsaicin VAS trajectory information achieved accuracy of 0.500, whereas the 8-minute and 20-minute windows achieved accuracies of 0.727 and 0.811, respectively. In contrast, prediction from baseline demographic, questionnaire, ECG, and EGG features alone was modest; the best-performing model was random forest with accuracy of 0.495 and balanced accuracy of 0.498.

Short-term direction prediction of VAS changes is reported in Figure 14 and Table S3. The logistic regression model achieved balanced accuracy of 0.711 and macro F1-score of 0.687, outperforming majority and persistence baselines.

### 3.6 Phenotype Prediction from Baseline Features

**Figure 7. Age distribution by temporal phenotype.**

![Figure 7. Age distribution by temporal phenotype.](data/figures/figure7_age_by_phenotype.png)

*Caption:* The figure shows age distributions by temporal phenotype.

*Abbreviations:* None.

**Figure 8. Standardized ECG/EGG feature distributions.**

![Figure 8. Standardized ECG/EGG feature distributions.](data/figures/figure8_ecg_egg_features.png)

*Caption:* The figure shows standardized ECG/EGG feature distributions by temporal phenotype.

*Abbreviations:* ECG, electrocardiogram; EGG, electrogastrography.

Baseline demographic and physiological variables showed only weak separation across temporal phenotypes. ECG/EGG-only phenotype prediction also remained modest; the best-performing ECG/EGG model was random forest with accuracy of 0.500 and balanced accuracy of 0.498. Feature importance and confusion matrix summaries are provided in Figures 15 and 16. These findings indicate that measured baseline characteristics and available physiological features do not strongly determine temporal phenotype membership in the present dataset.

## 4. Discussion

This study used an oral capsaicin-induced visceral pain model to characterize the temporal, spatial, and symptom-based organization of experimentally evoked upper gastrointestinal discomfort. The main findings were that capsaicin produced a reproducible biphasic VAS trajectory, that individual responses could be summarized by partially overlapping temporal phenotypes, that symptom–region associations converged predominantly on the right hypochondrium, that Rome IV-informed mapping identified biliary pain-like, bloating/distension-like, and IBS-like symptom patterns without constituting formal diagnoses, that short-term recovery transitions showed modest but measurable predictability, and that temporal phenotype membership was only weakly predicted from measured baseline demographic, questionnaire, ECG, and EGG features.

The rapid onset and gradual resolution of pain are consistent with the known excitatory and desensitizing properties of TRPV1 activation. The median time to pain onset was 1.0 minute, while median time to relief was 5.0 minutes, which reflects a clear temporal dissociation between the initial rise in pain and the subsequent resolution phase. The rapid onset likely reflects immediate nociceptor activation upon capsaicin exposure, while the gradual resolution may involve calcium-dependent desensitization processes and activation of descending inhibitory pathways. However, because the present study did not include autonomic, neuroimaging, or molecular measures, the biological mechanisms underlying individual temporal phenotypes remain inferential. The use of rank-based change point detection (PELT algorithm) provided objective temporal landmarks, with the majority of change points clustering around minute 5, corresponding to the transition from the ascending to the descending phase of pain.

Clustering analyses revealed that individual responses are heterogeneous and can be classified into distinct temporal phenotypes, including delayed-peak, early-sustained, and late-rising patterns. These temporal phenotypes should not be interpreted as fixed clinical subtypes. Rather, the fuzzy clustering results suggest that capsaicin-induced pain responses occupy a continuum, with individuals differing in the timing, persistence, and recovery profile of perceived pain. Traditional summary metrics such as AUC, peak VAS, and mean VAS would discard this temporal shape information, whereas DTW-based clustering captures morphological similarities despite differences in peak timing. Shapelet analysis further enhanced interpretability by identifying cluster-discriminative temporal motifs. These findings align with recent work on FGID subtyping, which has identified distinct patient clusters through nonlinear clustering of symptom severity profiles [22]. These temporal phenotypes may reflect differences in nociceptive activation, desensitization, symptom reporting, or attentional modulation; however, their biological correlates require validation using autonomic, neuroimaging, or molecular measures.

Symptom-based analyses showed that capsaicin-induced sensations are not randomly distributed but exhibit structured spatial–symptom coupling, with the right hypochondrium acting as a dominant symptom–region hub. The right hypochondrium exhibited the highest weighted degree (368) in the symptom-region network, followed by the hypogastrium (267) and abdominal distension (240). This centralized sensory organization is consistent with the expected physiological response to capsaicin stimulation, which primarily activates TRPV1-expressing afferents in the esophagus and stomach. Because symptom–region edges were generated from within-participant co-occurrence expansion, the resulting network reflects probabilistic symptom organization rather than direct anatomical localization. The convergence of multiple high-weight edges onto the right hypochondrium supports the presence of an upper abdominal-centered sensory axis, although this interpretation requires confirmation with objective physiological measures.

The Rome IV-informed mapping should be interpreted as a symptom-based alignment rather than a diagnostic classification. Because the present experimental protocol did not assess chronicity, symptom frequency over months, exclusion of structural disease, or clinical impairment, the observed biliary pain-like, bloating/distension-like, and IBS-like profiles indicate phenomenological overlap with Rome IV constructs rather than formal FGID diagnoses. The aim of Rome IV-informed mapping was not to diagnose FGIDs, but to evaluate whether experimentally induced symptom patterns resemble clinically recognized symptom constructs.

The prediction analysis should be regarded as exploratory. Although logistic regression outperformed baseline models for short-term VAS direction prediction (balanced accuracy = 0.711, macro F1 = 0.687), the magnitude of performance indicates modest local predictability rather than immediate clinical applicability. Its main value is to show that the recovery phase of capsaicin-induced pain contains temporal information that can be modeled prospectively. External validation and clinically meaningful prediction targets are required before translational use; the present analysis was designed to test whether local temporal structure exists in VAS trajectories rather than to develop a deployable clinical prediction model.

The phenotype prediction analysis indicates that measured baseline features do not strongly determine temporal phenotype membership in the present dataset. Random forest achieved the highest accuracy in the current baseline/physiology feature set, but performance remained modest (accuracy = 0.495; balanced accuracy = 0.498). This suggests that the temporal phenotypes capture response dynamics that are not well explained by static pre-experiment characteristics or the available physiological features.

This study illustrates the utility of integrating time-series, clustering, and network approaches for characterizing complex physiological data. The proposed multilayer framework links temporal dynamics, symptom expression, and clinical mapping into a scalable approach for dissecting inter-individual variability. Main methodological contributions include DTW-based modeling for variable temporal alignment, multilayer integration of symptom, region, and disease-construct information, shapelet analysis for interpretable feature extraction, and group-wise cross-validation to prevent information leakage. Although the oral capsaicin model provides a controlled method for inducing upper gastrointestinal discomfort, it remains an acute experimental model and should not be considered equivalent to chronic FGIDs.

Several limitations should be acknowledged. First, the acute capsaicin model does not capture the complexity of chronic functional gastrointestinal disorders, limiting generalizability to clinical populations; the Rome IV-informed mapping reflects symptom-based alignment rather than formal diagnosis, as it does not incorporate chronicity, symptom frequency, or exclusion of organic disease. Second, the analysis remained primarily exploratory, with clustering results sensitive to methodological choices and pattern stability across independent datasets yet to be established. Third, the self-reported VAS measurements are inherently subjective, and the study lacked multimodal physiological or neurobiological measures that could provide mechanistic insight into pain dynamics. Fourth, baseline phenotype prediction was limited by the available measured features and should not be interpreted as a deployable classification model. The absence of adverse events supports the tolerability of the 1 mg oral capsaicin protocol, although safety findings are limited by the sample size and acute observation period. Future work should integrate neuroimaging and autonomic data for mechanistic insight, extend to intervention studies evaluating treatment effects on temporal phenotypes, develop predictive models for clinical symptom trajectories, improve measurement of exposure history and physiological state, and validate identified clusters in independent samples.

In conclusion, the oral capsaicin model provides a controlled experimental window into the dynamic organization of visceral pain. By integrating time-series phenotyping, symptom–region network analysis, and Rome IV-informed mapping, this study shows that capsaicin-induced pain is structured by intensity, temporal trajectory, anatomical distribution, and symptom configuration. These findings support the use of dynamic analytical frameworks for studying experimental visceral pain and generating hypotheses relevant to FGID phenotyping.


## 5. Extended Methods

### 5.1 Study Design and Setting

This study employed an experimental observational design using an oral capsaicin-induced visceral pain model. The experiment was conducted under controlled conditions with a standardized protocol. Following oral administration of capsaicin, participants were monitored continuously for 20 minutes. Pain intensity was recorded at 1-minute intervals using a visual analog scale (VAS), generating individual time-series data.

### 5.2 Participants

A total of 216 participants were included in the analysis. All participants completed the capsaicin ingestion procedure and provided VAS ratings during the observation period. Participants with no reported pain (VAS consistently equal to 0) were retained in the dataset and treated as right-censored observations in time-to-event analyses.

### 5.3 Capsaicin Preparation and Administration (TIDieR Items 1-12)

**Brief Name (Item 1):** Oral Capsaicin Visceral Pain Model

**Rationale (Item 2):** The oral capsaicin model was selected because it provides a controlled, reproducible method for inducing upper gastrointestinal discomfort that mimics the symptom profiles reported by patients with functional gastrointestinal disorders. Capsaicin acts as a selective agonist of the TRPV1 channel, enabling mechanistically interpretable pain responses.

**Materials (Item 3):** Food-grade capsaicin (purity 98%; CAS No. 404-86-4; Ruimao Biotechnology Co., Ltd., Xi'an, China) was used as the solute. Capsaicin was dissolved in ethanol (96%, v/v; Spirytus Rektyfikowany, Polmos, Poland) to prepare a 1% (w/v) stock solution. For each administration, 10 μL of the solution (equivalent to 1 mg capsaicin) was encapsulated into a gastro-soluble gelatin capsule (gelatin; Xuanyu Plastic Products Factory, Taizhou, China).

**Procedures (Item 4):** The capsule was administered orally under direct observation by trained research staff. Following administration, participants were monitored continuously for 20 minutes in a controlled laboratory environment. Pain intensity was recorded at 1-minute intervals using a visual analog scale (VAS).

**Who Provided (Item 5):** The intervention was administered by trained research staff with experience in clinical research protocols. All staff received standardized training on capsaicin administration procedures and safety monitoring.

**How (Item 6):** The capsule was administered orally in a face-to-face setting. Participants were instructed to swallow the capsule with water.

**Where (Item 7):** The experiment was conducted in a controlled laboratory environment at [Institution Name].

**When and How Much (Item 8):** A single administration of 1 mg capsaicin was delivered. Following administration, participants were monitored for 20 minutes. Pain intensity was recorded at 1-minute intervals.

**Tailoring (Item 9):** No personalization or titration was applied. All participants received the same dose and protocol.

**Modifications (Item 10):** No modifications were made to the intervention during the course of the study.

**How Well - Planned (Item 11):** Adherence was assessed by direct observation of capsule administration. All participants were observed to complete the full administration protocol.

**How Well - Actual (Item 12):** All 216 participants completed the full capsaicin administration protocol without dose adjustments. No adverse events required protocol discontinuation.

### 5.4 Variables

Primary variables included pain intensity (VAS score) measured at each minute (1–20 min), pain onset time (first occurrence of increased VAS from baseline), pain relief time (first occurrence of sustained low VAS following peak), and total pain exposure quantified as area under the curve (AUC). Derived variables included first-order differences (slope), local summary statistics (mean, standard deviation, range), time-to-peak and peak intensity, cluster membership (pain phenotype), and binary direction outcome for prediction (increase vs decrease). Symptom variables included symptom categories (coded A–L), anatomical regions (coded 1–9), symptom–region co-occurrence pairs, and Rome IV-aligned FGID categories.

### 5.5 Data Preprocessing

Time-series preprocessing treated values marked "E" (early termination) and "T" (technical termination) as censored. Once an E or T marker appeared at any time point, all subsequent measurements for that participant were set to missing (NaN) and excluded from downstream analyses. Missing values were excluded from computations (e.g., mean, standard deviation) on a per-operation basis; no interpolation was applied to post-termination values.

Symptom and region codes were parsed at the character level (e.g., "12" → ["1", "2"]), standardized by removing delimiters, mapped to predefined labels, and deduplicated within participants to ensure each symptom–region pair appeared only once per participant.

### 5.6 Pain Onset Detection

Pain onset was determined using three complementary approaches: (1) threshold-based method (VAS > 3), (2) first-difference method (ΔVAS ≥ 0.5 between consecutive minutes), and (3) change point detection using the PELT algorithm (rank-based model, penalty = 0.5) [37].

### 5.7 Survival Analysis

Kaplan–Meier methods were used to estimate time to pain onset and time to pain relief. Median survival times and 95% confidence intervals were calculated using the Greenwood estimator. To assess the temporal relationship between the onset and resolution phases, the distributions of pain onset times and pain relief times were compared using the log-rank test (α = 0.05). This test evaluates whether the two event types (onset vs relief) follow different time-to-event distributions within the same cohort, rather than comparing between independent groups.

### 5.8 Quantification of Pain Exposure

Total pain exposure was quantified using the area under the curve (AUC), computed using the trapezoidal rule. Peak VAS and time-to-peak were extracted from the time series.

### 5.9 Clustering Analysis

Time-series clustering was performed using DTW-based K-means clustering with DTW barycentric averaging (DBA) centroids and DTW-based fuzzy c-medoids clustering (m = 2), drawing on established DTW and fuzzy objective-function approaches [34-36]. Silhouette analysis was conducted to characterize cluster separation for the three-cluster solution.

### 5.10 Feature Extraction

Cluster-specific temporal features were extracted using shapelet analysis, identifying discriminative subsequences that characterize local temporal dynamics [38]. Shapelet extraction used DTW-based distance computation with minimum subsequence length of 5, maximum length of 5, and retention of the top 3 shapelets per cluster. Redundant shapelets with correlation above 0.90 were removed to ensure diversity.

### 5.11 Symptom Data Encoding and Preprocessing

Participant-reported gastrointestinal symptoms were recorded using a predefined coding system, in which each symptom was represented by a single uppercase letter (A–L) and each anatomical region by a numeric code (1–9). Symptom codes corresponded to standardized symptom descriptors (e.g., abdominal pain, heartburn, nausea), while region codes represented abdominal topography (e.g., epigastrium, umbilical, hypogastrium).

To ensure consistent downstream analysis, coded entries were parsed using a character-level decoding strategy. Specifically, compact representations (e.g., "12") were decomposed into individual codes (["1", "2"]), and mixed formats with delimiters (e.g., "1;2", "A/C") were normalized by removing separators and splitting into single-character tokens. Invalid or undefined codes were excluded based on predefined codebooks. Within each participant, duplicate codes were removed while preserving the original order of appearance.

Decoded symptom and region codes were then mapped to their corresponding standardized textual labels using predefined dictionaries. This process produced, for each participant, a structured list of normalized symptoms and anatomical regions suitable for quantitative analysis.

### 5.12 Construction of Symptom–Region Associations

A bipartite representation of symptom–region relationships was constructed at the participant level. For each individual, all pairwise combinations between reported symptoms and anatomical regions were generated. To reduce within-subject redundancy, repeated symptom–region pairs were collapsed into a single occurrence per participant.

Across the cohort, these pairwise associations were aggregated to form a weighted symptom–region matrix in which each cell represented the frequency of co-occurrence between a given symptom and anatomical region. This matrix served as the basis for subsequent network and heatmap analyses.

### 5.13 Rome IV-Informed Symptom Pattern Mapping

Participant-level symptom profiles were mapped to functional gastrointestinal disorder (FGID) categories based on Rome IV criteria using a rule-based scoring framework. For each FGID category, diagnostic rules were defined in terms of required symptoms, supportive symptoms, required anatomical regions, and supportive anatomical regions. This procedure represents symptom-based alignment with Rome IV-defined categories rather than formal clinical diagnosis.

### 5.14 Tripartite Network Construction

A tripartite network was constructed comprising three node types: symptoms, anatomical regions, and Rome IV-aligned FGID categories, extending prior network approaches to symptom and disease organization [39-41]. Edges were defined as symptom–region edges (co-occurrence within participants), symptom–disease edges (linking symptoms to FGID categories), and region–disease edges (linking anatomical regions to FGID categories).

### 5.15 Short-Term Direction Prediction

A sliding-window classification framework was implemented to predict whether the VAS score would decrease at the next time point. For each participant, the continuous VAS time series was segmented into overlapping windows of length 3. The primary outcome was defined as a binary variable indicating whether the VAS score decreased at the next minute.

Feature inputs included recent VAS values within the window, first-order difference (local slope), time index (minute), local summary statistics (mean, standard deviation, range), distance to local extrema (maximum/minimum), monotonicity indicators within the window, and subject-level phenotype features (average VAS and cluster label).

Three models were evaluated: (1) majority classifier, (2) persistence direction model, and (3) logistic regression model with class balancing. Model performance was assessed using accuracy, balanced accuracy, macro F1-score, and weighted F1-score. Group-wise cross-validation was employed to prevent information leakage from repeated measures.

### 5.16 Phenotype Prediction from Baseline Features

To assess whether temporal pain phenotypes could be predicted from pre-experiment characteristics, we trained classifiers to predict cluster membership using baseline demographic, questionnaire, electrocardiogram (ECG), and electrogastrography (EGG) data. Demographic and questionnaire features included age, sex, body mass index, height, weight, alcohol consumption, spicy food habits (frequency, usual spiciness level, preference, maximum tolerance), Chronic Capsaicin Exposure Index (CCEI), Acute Exposure Score (AES), recent spicy food intake (24 h), spicy episodes (24 h), baseline gastrointestinal symptoms, and time since last meal. ECG-derived features included heart rate variability parameters (SDNN, RMSSD, pNN50, pNN20, CVSD, LF power, HF power, LF/HF ratio, LFnu, HFnu, SD1, SD2, SD1/SD2 ratio), heart rate variability (HR_sd, HR_cv), and ECG signal quality indicators (ECG_SQI, ECG_artifact_ratio, ECG_RR_edit_ratio). EGG-derived features included dominant frequency, mean and median frequency, dominant power, total power, percentages of normogastria/bradygastria/tachygastria, power ratio, spectral entropy, spectral flatness, dominant frequency instability, signal energy, RMS, and EGG signal quality. ECG–EGG coupling features included cross-correlation maximum, lag, coherence mean, energy ratio, and HR–EGG correlation. After preprocessing and encoding, the phenotype-prediction dataset contained 66 input features. Missing values were imputed with column medians.

Six model architectures were evaluated: (1) logistic regression with balanced class weights, (2) random forest with balanced class weights (200 trees, maximum depth 5), (3) gradient boosting (100 trees, maximum depth 3), (4) histogram-based gradient boosting (maximum iterations 200, maximum depth 5), (5) a multi-layer perceptron with early stopping (hidden layers of 64 and 32 units, maximum iterations 1000, validation fraction 0.1), and (6) a stacking ensemble combining logistic regression, random forest, support vector machine with radial basis function kernel, and histogram-based gradient boosting as base learners, with logistic regression as the meta-learner. Model performance was assessed using stratified ten-fold cross-validation. Primary evaluation metrics were balanced accuracy and macro F1-score. Confusion matrices were computed from out-of-fold predictions across all folds. Feature importance was derived from random forest feature importances.

### 5.17 Statistical Considerations

All analyses were conducted at the participant level, with aggregation performed across the study cohort. Edge weights and matrix values represent frequency counts rather than probabilities. No formal statistical inference was performed at this stage; instead, the analysis focused on descriptive pattern extraction and structural relationships among symptoms, regions, and disease categories.

### 5.18 Safety Monitoring and Adverse Event Assessment

Adverse events were monitored throughout the experimental session. An adverse event was defined as any unfavorable or unintended medical occurrence during or after capsaicin administration that exceeded the expected transient gastrointestinal sensations induced by the experimental model, required medical intervention, led to protocol discontinuation, or resulted in clinically significant discomfort or risk.

Expected capsaicin-induced sensations, including transient heartburn, abdominal pain, abdominal distension, nausea, or related gastrointestinal discomfort, were recorded as study outcomes rather than adverse events unless they were severe, prolonged, required clinical treatment, or led to early termination of the experimental protocol.

All participants were observed during the 20-minute post-administration assessment period. The occurrence, severity, duration, relatedness to capsaicin administration, required intervention, and outcome of any adverse events were planned to be recorded. Serious adverse events were defined as events resulting in death, life-threatening condition, hospitalization, persistent disability, or any medically significant condition requiring urgent intervention.

### 5.19 Figure Organization

The manuscript contains sixteen sequentially numbered figures. All figures are single-panel displays without combined layouts or subfigure labels:

- **Figure 1:** group mean VAS trajectory.
- **Figure 2:** temporal pain phenotype trajectories.
- **Figure 3:** symptom burden.
- **Figure 4:** pain region burden.
- **Figure 5:** early VAS window phenotype classification.
- **Figure 6:** baseline and physiological phenotype prediction.
- **Figure 7:** age distribution by temporal phenotype.
- **Figure 8:** standardized ECG/EGG feature distributions.
- **Figure 9:** onset and change-point timing.
- **Figure 10:** Kaplan-Meier event curves for onset and relief.
- **Figure 11:** cluster-specific shapelets.
- **Figure 12:** symptom-region co-occurrence heatmap.
- **Figure 13:** symptom-Rome IV co-occurrence heatmap.
- **Figure 14:** short-term VAS direction classification performance.
- **Figure 15:** ECG/EGG random forest feature importance.
- **Figure 16:** ECG/EGG phenotype prediction confusion matrix.

## 6. Extended Results

### 6.1 Pain Onset Detection

#### 6.1.1 Group-Level VAS Trajectory

To characterize the group-level dynamics of pain intensity, visual analog scale (VAS) scores were plotted over a 20-minute period following oral capsaicin administration, with error bars representing the standard error of the mean (SEM) and superimposed sample size histogram for each time point.

The average VAS score increased sharply within the first 2–4 minutes, peaking at 4.22 at minute 4, suggesting rapid perception of discomfort after capsaicin exposure. After this peak, scores gradually declined from minute 5 to minute 15 and stabilized around 3.0. This trajectory reflects a biphasic pain response: an acute escalation phase followed by gradual adaptation or desensitization.

The vertical histogram bars indicate a decreasing number of contributing participants over time, particularly beyond minute 15, due to early or technical termination markers encoded as "E" or "T". The overall declining trend remained visible despite this reduction in available observations.

#### 6.1.2 Change Point Analysis

To complement threshold-based onset definitions, change-point detection was used to identify time points where the distributional characteristics of the VAS series changed abruptly. The rank-based PELT (Pruned Exact Linear Time) algorithm was applied with a penalty parameter of 0.5.

The analysis was conducted across 216 individual VAS time series following capsaicin ingestion. Change points were detected independently for each participant, and the resulting distribution is presented in Figure 9.

**Figure 9. Onset and change-point timing.**

![Figure 9. Onset and change-point timing.](data/figures/figure9_onset_timing.png)

*Caption:* This figure summarizes threshold-defined onset, derivative-defined onset, and PELT-derived change-point timing for individual VAS trajectories after capsaicin administration.

*Abbreviations:* PELT, Pruned Exact Linear Time; VAS, visual analog scale.

The majority of detected change points clustered around time index 5 (corresponding to minute 5 post-exposure), with over 40 subjects exhibiting detected shifts in pain trajectory at this point. Additional, less frequent clusters were observed at index 10 (minute 10) and index 15 (minute 15), affecting 11 and 4 subjects, respectively. Very few or no change points were identified outside of these time windows.

This temporal pattern is consistent with the group-level VAS trajectory; pain intensities rise rapidly in the first 4–5 minutes, peak around minute 4–5, and then decline gradually. The early change point concentration reflects the transition from the ascending to the descending phase of pain, while the later detections may correspond to secondary transitions or resolution phases in individual responses.

The use of rank-based cost functions allows for robust, nonparametric segmentation that is less sensitive to outliers and irregular variance, making it particularly suited for heterogeneous physiological data such as subjective pain ratings.

### 6.2 Survival Analysis

Kaplan-Meier survival curves were computed using the lifelines Python package. Median survival times and 95% confidence intervals were estimated using the Greenwood formula. To assess the temporal relationship between the onset and resolution phases, the distributions of pain onset times and pain relief times were compared using the log-rank test (α = 0.05), which evaluates whether the two event types follow different time-to-event distributions within the same cohort.

To delineate the temporal pattern of capsaicin-induced pain, we conducted Kaplan-Meier survival analyses for two events: (1) pain onset, defined as the first occurrence of a visual analog scale (VAS) score exceeding 3; and (2) pain relief, defined as the first instance post-peak where the VAS score dropped below 1. A total of 216 participants were included in the analysis, with VAS scores collected at one-minute intervals over a 20-minute observation period.

As shown in Figure 10, the survival curve for VAS > 3 (pain onset) declined sharply in the early minutes. The median onset time was 1.0 minute, indicating rapid perception of discomfort shortly after capsaicin exposure. In contrast, the survival curve for VAS < 1 (pain relief) showed a delayed and gradual descent, with a median relief time of 5.0 minutes.

**Figure 10. Kaplan-Meier event curves for onset and relief.**

![Figure 10. Kaplan-Meier event curves for onset and relief.](data/figures/figure10_survival_curves.png)

*Caption:* Kaplan-Meier curves show time to pain onset and time to pain relief after oral capsaicin administration, allowing comparison of the onset and resolution phases.

*Abbreviations:* KM, Kaplan-Meier; VAS, visual analog scale.

The difference between onset and relief distributions was supported by the log-rank test (p < 0.0001), reflecting a temporal dissociation between the initial rise in pain and the subsequent resolution phase. This biphasic trajectory supports the suitability of the capsaicin model for capturing both acute nociceptive activation and later desensitization or adaptation.

### 6.3 Quantification of Pain Exposure

The area under the curve (AUC) of pain intensity was used to quantify the integrated exposure of pain intensity and duration over the entire 20-minute observation period. The AUC is expressed in units of VAS·time (minutes), with higher values indicating greater cumulative pain experienced by the subject. Mean group-level VAS scores were computed at 1-minute intervals following exclusion of 'E'/'T' flags. Area under the curve (AUC) was computed using numpy.trapezoid. Peak VAS intensity and peak time were extracted using numpy.nanmax and index mapping.

To quantify the aggregate pain experience following capsaicin exposure, we analyzed the group-level mean trajectory of visual analog scale (VAS) scores across 216 participants (Figure 1). The VAS data were pre-processed to address censoring events (e.g., early termination), and values marked as 'E' or 'T' were excluded from computation.

The mean VAS increased rapidly during the first 4 minutes, reaching a peak intensity of 4.22 at minute 4, after which it gradually declined. The pain response persisted across the full 20-minute observation window, with non-zero group-level VAS values maintained for 19 minutes, indicating a prolonged symptomatic phase.

The area under the curve (AUC), which reflects the cumulative pain burden across the cohort, was calculated using the trapezoidal method and was 64.56. This metric integrates both the magnitude and duration of pain and may be a robust outcome indicator for between-group comparisons or treatment effects.

The observed pain trajectory demonstrates the biphasic profile typically associated with oral capsaicin models: an acute onset of discomfort followed by gradual desensitization. This pattern confirms the model's utility in capturing dynamic nociceptive processes at the group level.

### 6.4 Clustering Analysis

To group subjects based on the shape of their VAS time series and identify typical pain response patterns according to the dynamic morphology of pain curves, we employed a shape-based clustering approach for time series. Because the timing of peak pain intensity may vary across subjects, directly computing pointwise Euclidean distances may underestimate shape similarity. Therefore, the dynamic time warping (DTW) distance was adopted as the distance metric between time series. By allowing flexible alignment along the time axis, DTW can match similar morphological components between two curves, even when they are temporally misaligned.

K-means clustering (DTW version): DTW distance is used in place of Euclidean distance, and cluster centroids (average curves) are computed during the clustering process using the DTW Barycentric Averaging (DBA) algorithm. This approach enables iterative refinement to obtain K clusters; the centroid curve of each cluster represents a typical pain pattern.

To handle irregular termination patterns in VAS time series, values marked as "E" (early termination) or "T" (technical termination) were treated as censored. Once an E or T marker appeared at any time point, all subsequent measurements for that participant were set to missing (NaN), effectively removing post-termination data from all downstream analyses. Missing values were excluded from computations (e.g., mean, standard deviation) on a per-operation basis.

Time-series clustering using dynamic time warping (DTW) and DTW barycentric averaging (DBA) identified three distinct temporal patterns of pain trajectories. Each curve represents the centroid (prototype) of a cluster, summarizing the characteristic temporal evolution of pain intensity across subjects within that group. Cluster 1 (n = 77) exhibited a delayed peak followed by a gradual decline (delayed-peak responders), Cluster 2 (n = 77) showed an early rise with sustained moderate intensity (early-sustained responders), and Cluster 3 (n = 62) demonstrated a gradual increase with late-phase elevation (late-rising responders). These patterns indicate heterogeneous temporal dynamics in pain responses across individuals.

Silhouette coefficients for individual subjects are displayed for each cluster based on pairwise DTW distances. Most samples exhibited positive silhouette values, indicating appropriate cluster assignment. The dashed line represents the average silhouette score (0.318), which reflects moderate but meaningful cluster separation.

The average silhouette coefficient was computed using pairwise dynamic time warping (DTW) distances for the three-cluster solution (K = 3). The silhouette value of 0.318 indicates moderate but meaningful cluster separation. For comparison, silhouette values for candidate cluster solutions ranging from K = 2 to K = 6 were examined, with K = 3 showing the highest value, which is consistent with the three-cluster structure described in the primary analysis.

To account for uncertainty in cluster assignment, we also performed a fuzzy clustering analysis based on dynamic time warping (DTW). Because conventional fuzzy c-means assumes Euclidean geometry, a DTW-based fuzzy c-medoids algorithm was employed, in which each subject was assigned a membership value for each cluster. The fuzziness parameter was set to m = 2, and clustering was performed using the same number of clusters (K = 3) as determined in the primary analysis.

Fuzzy clustering of pain trajectories using dynamic time warping (DTW) identified three representative temporal patterns. Each curve corresponds to the medoid trajectory of a cluster, representing the most central subject within that group. The final hard-label distribution from the updated analysis was 77, 77, and 62 participants across the three temporal phenotypes. These results indicate heterogeneous temporal dynamics of pain responses across subjects.

Histogram of membership values for each cluster obtained from DTW-based fuzzy c-medoids clustering. Most subjects exhibited intermediate membership values (0.2–0.5), indicating partial association with multiple clusters. This suggests that pain response patterns form a continuum rather than strictly discrete categories.

The objective function decreased rapidly during the first iterations and stabilized thereafter, indicating efficient convergence to a stable solution. No oscillation or divergence was observed, supporting the robustness of the clustering procedure.

Together, these findings suggest that temporal pain responses are better characterized as a spectrum of partially overlapping patterns rather than strictly discrete classes.

### 6.5 Feature Extraction

To improve the interpretability of clustering results, shapelets were extracted as local subsequences representative of each temporal phenotype. These subsequences identify the trajectory fragments that best differentiate each cluster from the remaining series and provide a local feature signature for each response pattern.

Shapelet analysis revealed cluster-specific temporal motifs that further clarified the structure of the identified pain phenotypes (Figure 11). Cluster 1 was characterized by shapelets reflecting delayed peaks and subsequent decline, Cluster 2 exhibited sustained or plateau-like patterns, and Cluster 3 showed shapelets representing gradual increases in signal intensity, consistent with delayed or accumulating responses. These findings indicate that the observed clustering structure is driven by distinct local temporal dynamics rather than global amplitude differences.

**Figure 11. Cluster-specific shapelets.**

![Figure 11. Cluster-specific shapelets.](data/figures/figure11_shapelets.png)

*Caption:* Cluster-discriminative shapelets illustrate local temporal motifs that distinguish delayed-peak, early-sustained, and late-rising VAS response phenotypes.

*Abbreviations:* VAS, visual analog scale.

These results suggest that pain responses are not solely defined by peak intensity, but by the temporal organization of response phases, including onset speed, persistence, and recovery dynamics.

### 6.6 Symptom Data Encoding and Preprocessing

Participant-reported gastrointestinal symptoms were recorded using a predefined coding system, in which each symptom was represented by a single uppercase letter (A–L) and each anatomical region by a numeric code (1–9). Symptom codes corresponded to standardized symptom descriptors (e.g., abdominal pain, heartburn, nausea), while region codes represented abdominal topography (e.g., epigastrium, umbilical, hypogastrium).

To ensure consistent downstream analysis, coded entries were parsed using a character-level decoding strategy. Specifically, compact representations (e.g., "12") were decomposed into individual codes (["1", "2"]), and mixed formats with delimiters (e.g., "1;2", "A/C") were normalized by removing separators and splitting into single-character tokens. Invalid or undefined codes were excluded based on predefined codebooks. Within each participant, duplicate codes were removed while preserving the original order of appearance.

Decoded symptom and region codes were then mapped to their corresponding standardized textual labels using predefined dictionaries. This process produced, for each participant, a structured list of normalized symptoms and anatomical regions suitable for quantitative analysis.

### 6.7 Construction of Symptom–Region Associations

A bipartite representation of symptom–region relationships was constructed at the participant level. For each individual, all pairwise combinations between reported symptoms and anatomical regions were generated. To reduce within-subject redundancy, repeated symptom–region pairs were collapsed into a single occurrence per participant.

Across the cohort, these pairwise associations were aggregated to form a weighted symptom–region matrix in which each cell represented the frequency of co-occurrence between a given symptom and anatomical region. This matrix served as the basis for subsequent network and heatmap analyses.

Descriptive statistics and co-occurrence analyses were performed on symptom descriptors collected during the capsaicin induction experiment to summarize common symptom categories and their anatomical distributions.

A total of 216 symptom reports were analyzed to characterize the distribution of capsaicin-induced visceral sensations across anatomical regions. Overall, abdominal distension was the most frequently reported symptom (154/216, 71.3%), followed by nausea (85/216, 39.4%) and abdominal pain (84/216, 38.9%). Other symptoms, including acid regurgitation, vomiting, bloating, palpitations, and belching, were reported at lower frequencies.

Symptom perception was predominantly localized to the right hypochondrium (140/216, 64.8%) and hypogastrium (92/216, 42.6%), followed by the left hypochondrium and right lumbar regions. Inguinal, epigastric, and umbilical regions were infrequently reported in the current coded dataset.

The co-occurrence heatmap further demonstrated region-specific symptom patterns (Figure 12). The right hypochondrium and hypogastrium had the densest symptom co-occurrence counts, especially for abdominal distension, nausea, and abdominal pain. These patterns should be interpreted as co-occurrence structure derived from participant-reported symptom and region codes rather than direct anatomical localization.

**Figure 12. Symptom-region co-occurrence heatmap.**

![Figure 12. Symptom-region co-occurrence heatmap.](data/figures/figure12_symptom_region_heatmap.png)

*Caption:* The heatmap shows participant-level co-occurrence counts between reported symptom categories and anatomical regions after capsaicin administration.

*Abbreviations:* None.

Certain regions (e.g., right inguinal) exhibited sparse but highly specific symptom patterns due to limited sample counts and should be interpreted cautiously. Overall, these findings indicate that capsaicin-induced sensations are not randomly distributed, but instead exhibit spatial–symptom coupling patterns consistent with structured visceral sensory organization.

All analyses were based on co-occurrence expansion, whereby multiple symptoms and regions reported by a single participant were included as all possible combinations. Therefore, the heatmap reflects relative co-occurrence patterns rather than one-to-one symptom–region correspondence.

### 6.8 Co-occurrence Network Analysis

Co-occurrence network analysis characterized structural relationships among symptom categories and anatomical regions. Nodes represented symptoms or abdominal regions, and edges represented within-participant co-occurrence. Edge weights corresponded to the number of participants in whom paired features co-occurred. Co-occurrence statistics were derived directly from the experimental dataset without external priors, so dense local subnetworks should be interpreted as recurrent perceptual profiles rather than anatomical pathways.

The overall bipartite co-occurrence network revealed a highly structured pattern of symptom–region associations. The strongest edge was observed between abdominal distension and the right hypochondrium (weight = 110), which indicates that abdominal distension was predominantly localized to the right upper abdominal region. A secondary association was observed between abdominal distension and the hypogastrium (weight = 59), followed by abdominal pain and the right hypochondrium (weight = 53).

Other prominent associations included nausea and the right hypochondrium (weight = 52) and nausea and the hypogastrium (weight = 47). These findings collectively indicate that multiple symptom modalities converge on the right hypochondrium and hypogastrium in the current coded dataset.

Node-level analysis further demonstrated that the right hypochondrium exhibited the highest weighted degree (368), identifying it as the dominant hub of the network. This was followed by the hypogastrium (267), abdominal distension (240), nausea (145), and abdominal pain (143).

Overall, the network structure suggests centralized symptom organization, characterized by a dominant right-hypochondrial hub and secondary involvement of the hypogastrium and adjacent abdominal regions. The convergence of multiple high-weight edges onto these regions supports the presence of a structured upper-abdominal sensory axis, consistent with the expected physiological response to capsaicin stimulation.

**Table S1. Top 5 symptom–region associations of Overall Symptom–Region network**

| Symptom | Region | Weight |
|---------|--------|--------|
| Abdominal distension | Right hypochondrium | 110 |
| Abdominal distension | Hypogastrium | 59 |
| Abdominal pain | Right hypochondrium | 53 |
| Nausea | Right hypochondrium | 52 |
| Nausea | Hypogastrium | 47 |

**Table S2. Top 5 network nodes of Overall Symptom–Region network**

| Node | Type | Degree | Weighted Degree |
|------|------|--------|-----------------|
| Right hypochondrium | region | 12 | 368 |
| Hypogastrium | region | 12 | 267 |
| Abdominal distension | symptom | 8 | 240 |
| Nausea | symptom | 9 | 145 |
| Abdominal pain | symptom | 7 | 143 |

### 6.9 Rome IV-Informed Symptom Pattern Mapping

Participant-level symptom profiles were mapped to functional gastrointestinal disorder (FGID) categories based on Rome IV criteria using a rule-based scoring framework. For each FGID category, diagnostic rules were defined in terms of required symptoms, supportive symptoms, required anatomical regions, and supportive anatomical regions. This procedure represents symptom-based alignment with Rome IV-defined categories rather than formal clinical diagnosis.

#### 6.9.1 Symptom–Region Associations

Analysis of the symptom–region frequency matrix revealed a non-uniform spatial distribution of gastrointestinal symptoms. The right hypochondrium emerged as the predominant anatomical locus, exhibiting the highest frequency of associations across multiple symptoms, particularly abdominal distension, nausea, and abdominal pain. The hypogastrium also demonstrated substantial involvement. In contrast, inguinal, epigastric, and umbilical regions showed relatively sparse symptom representation in the current coded dataset.

#### 6.9.2 Symptom–Disease Mapping

Mapping of symptom profiles to Rome IV-aligned categories demonstrated distinct patterns of association (Figure 13). Abdominal distension and abdominal pain contributed broadly to biliary pain-like, bloating/distension-like, and IBS-like alignments. Nausea and vomiting contributed to upper gastrointestinal symptom-pattern alignment, whereas bloating and abdominal distension were primarily associated with functional abdominal bloating/distension-like patterns.

**Figure 13. Symptom-Rome IV co-occurrence heatmap.**

![Figure 13. Symptom-Rome IV co-occurrence heatmap.](data/figures/figure13_symptom_rome_heatmap.png)

*Caption:* The heatmap shows associations between reported symptom categories and Rome IV-informed symptom-pattern alignments generated by the rule-based mapping framework.

*Abbreviations:* FGID, functional gastrointestinal disorder.

#### 6.9.3 Region–Disease Relationships

Integration of anatomical information revealed that disease associations were strongly region-dependent. The right hypochondrium demonstrated the highest connectivity across multiple Rome IV-informed symptom-pattern categories, particularly biliary pain-like and bloating/distension-like alignments. The hypogastrium showed moderate associations with IBS-like and bloating-related conditions. Lower abdominal regions, including inguinal areas, exhibited weaker but more specific associations.

#### 6.9.4 Network-Level Integration

The tripartite network analysis revealed a densely interconnected structure linking symptoms, anatomical regions, and disease categories. Symptom-region associations formed a tightly coupled module centered on the right hypochondrium and hypogastrium and were associated with biliary pain-like, bloating/distension-like, and IBS-like symptom-pattern alignments. Lower-frequency symptoms exhibited more diffuse connectivity patterns with weaker category specificity.

The network also highlighted overlapping symptom contributions across multiple disease categories, which reflects the inherent heterogeneity and shared symptomatology of FGIDs.

#### 6.9.5 Distribution of FGID Categories

At the cohort level, biliary pain-like profiles were the most frequently assigned category (26.4%, 57/216), followed by functional abdominal bloating/distension-like (16.2%, 35/216), IBS-like (11.6%, 25/216), unspecified functional GI symptom pattern (5.1%, 11/216), functional constipation/defecatory disorder-like (2.3%, 5/216), and functional dyspepsia-PDS-like (0.5%, 1/216).

### 6.10 Short-Term Direction Prediction

To evaluate the short-term predictability of symptom dynamics, a sliding-window classification framework was implemented to predict whether the VAS score would decrease at the next time point.

For each participant, the continuous VAS time series (1–20 minutes) was segmented into overlapping windows of length 3. For each window, the preceding three observations [VAS_{t-2}, VAS_{t-1}, VAS_t] were used to predict the direction of change at the subsequent time point.

The primary outcome was defined as a binary variable indicating whether the VAS score decreased at the next minute:

$$y = \begin{cases} 1, & \text{if } VAS_{t+1} < VAS_t \\ 0, & \text{otherwise} \end{cases}$$

Feature inputs included recent VAS values within the window, local slope (least-squares linear regression slope over the 3-point window), time index (minute), local summary statistics (mean, standard deviation, range), distance to local extrema (maximum/minimum), monotonicity indicators within the window, and subject-level phenotype features (average VAS and cluster label). Categorical variables were one-hot encoded.

To avoid information leakage across repeated measures, model evaluation was conducted using group-wise cross-validation, with all samples from the same participant assigned to the same fold.

Three models were evaluated: (1) majority classifier (predicting the most frequent class), (2) persistence direction model (predicting the next direction based on the current slope), and (3) logistic regression model with class balancing.

Model performance was assessed using accuracy, balanced accuracy, macro F1-score, and weighted F1-score. Balanced accuracy and macro F1-score were emphasized due to class imbalance.

**Figure 14. Short-term VAS direction classification performance.**

![Figure 14. Short-term VAS direction classification performance.](data/figures/figure14_direction_classification.png)

*Caption:* Classification performance is shown for short-term prediction of whether the next VAS value would decrease, comparing majority, persistence-direction, and logistic regression models.

*Abbreviations:* VAS, visual analog scale.

**Table S3. Performance of short-term direction prediction models**

| Model | Accuracy (mean ± SD) | Balanced Accuracy | Macro F1 | Weighted F1 |
|-------|---------------------|-------------------|----------|-------------|
| Majority | 0.717 ± 0.016 | 0.500 ± 0.000 | 0.418 ± 0.005 | 0.599 ± 0.021 |
| PersistenceDir | 0.579 ± 0.032 | 0.531 ± 0.025 | 0.523 ± 0.025 | 0.594 ± 0.031 |
| Logistic | 0.722 ± 0.030 | 0.711 ± 0.016 | 0.687 ± 0.022 | 0.732 ± 0.026 |

Across group-wise cross-validation, the logistic regression model achieved superior performance compared to baseline models, with balanced accuracy of 0.711 and macro F1-score of 0.687. In contrast, the majority classifier achieved high overall accuracy (0.717) but failed to identify descending transitions (balanced accuracy = 0.500), which reflects class imbalance.

The persistence-based model, which predicts the next direction based on the current slope, demonstrated moderate performance (balanced accuracy = 0.531).

The logistic regression model improved detection of descending transitions, achieving higher recall for the decrease class. This finding indicates that entry into the recovery phase is partially predictable from recent trajectory patterns.

Compared with the previous three-state direction prediction approach, binary classification of descending transitions produced higher performance. Recovery-related dynamics showed stronger local predictability than fine-grained directional fluctuations in the present dataset.

### 6.11 Phenotype Prediction from Baseline Features

To assess whether the temporal pain phenotypes identified by DTW-based clustering could be predicted from pre-experiment characteristics, we trained six classifiers to predict cluster membership using baseline demographic, questionnaire, ECG, and EGG data.

Across stratified ten-fold cross-validation on the observed dataset, none of the models achieved strong predictive performance. Random forest achieved the highest accuracy (0.495 ± 0.071) and balanced accuracy (0.498 ± 0.073), followed by gradient boosting (accuracy = 0.473; balanced accuracy = 0.466) and stacking (accuracy = 0.453; balanced accuracy = 0.463).

**Table S4. Phenotype prediction from baseline and physiological features**

| Model | Accuracy (mean ± SD) | Balanced Accuracy | Macro F1 | Weighted F1 |
|-------|---------------------|-------------------|----------|-------------|
| Logistic Regression | 0.384 ± 0.110 | 0.388 ± 0.107 | 0.369 ± 0.100 | 0.367 ± 0.102 |
| Random Forest | 0.495 ± 0.071 | 0.498 ± 0.073 | 0.490 ± 0.081 | 0.490 ± 0.079 |
| Gradient Boosting | 0.473 ± 0.098 | 0.466 ± 0.095 | 0.459 ± 0.098 | 0.462 ± 0.099 |
| HistGradientBoosting | 0.444 ± 0.095 | 0.440 ± 0.093 | 0.438 ± 0.097 | 0.439 ± 0.098 |
| MLP | 0.291 ± 0.079 | 0.309 ± 0.061 | 0.235 ± 0.099 | 0.227 ± 0.111 |
| Stacking | 0.453 ± 0.047 | 0.463 ± 0.053 | 0.450 ± 0.046 | 0.445 ± 0.044 |

For a three-class problem with approximately balanced classes, chance-level balanced accuracy is 0.333. The ECG/EGG feature importance and confusion matrix analyses are shown in Figures 15 and 16.

**Figure 15. ECG/EGG random forest feature importance.**

![Figure 15. ECG/EGG random forest feature importance.](data/figures/figure15_ecg_feature_importance.png)

*Caption:* Random forest feature importance values summarize the relative contribution of ECG, EGG, and ECG-EGG coupling features to temporal phenotype prediction.

*Abbreviations:* ECG, electrocardiogram; EGG, electrogastrography.

**Figure 16. ECG/EGG phenotype prediction confusion matrix.**

![Figure 16. ECG/EGG phenotype prediction confusion matrix.](data/figures/figure16_ecg_confusion_matrix.png)

*Caption:* The confusion matrix shows out-of-fold temporal phenotype predictions from the ECG/EGG-based classification model.

*Abbreviations:* ECG, electrocardiogram; EGG, electrogastrography.

These observed-data findings indicate that the temporal pain phenotypes are not strongly determined by the measured pre-experiment demographic characteristics, dietary habits, baseline symptom profiles, HRV parameters, or ECG–EGG coupling metrics.

### 6.12 Safety and Adverse Events

No adverse events or serious adverse events occurred during the study. No participant required medical intervention, unplanned clinical care, hospitalization, or discontinuation of the protocol due to safety concerns. Expected transient gastrointestinal sensations induced by capsaicin were recorded as study outcomes and were not classified as adverse events unless they exceeded the anticipated response profile or required clinical management; no such cases were observed.

**Table S5. Summary of adverse events**

| Safety outcome | Number of participants | Percentage |
|---|---:|---:|
| Any adverse event | 0 | 0.0% |
| Serious adverse event | 0 | 0.0% |
| Medical intervention required | 0 | 0.0% |
| Protocol discontinuation due to adverse event | 0 | 0.0% |
| Hospitalization | 0 | 0.0% |

Expected transient capsaicin-induced gastrointestinal sensations were analyzed as study outcomes and were not classified as adverse events unless they required clinical intervention, led to protocol discontinuation, or exceeded the anticipated response profile.

## 7. Extended Discussion

### 7.1 Principal Findings

This study provides a comprehensive, multi-dimensional characterization of oral capsaicin-induced visceral pain by integrating time-series modeling, clustering analysis, symptom-network mapping, and predictive modeling. The principal findings include biphasic temporal structure of capsaicin-induced pain, identification of distinct temporal phenotypes (delayed-peak, early-sustained, late-rising), central role of the right hypochondrium in the symptom–region network, Rome IV-informed symptom categories dominated by biliary pain-like, functional abdominal bloating/distension-like, and IBS-like patterns, evidence of short-term predictability in recovery dynamics, and weak observed-data prediction of temporal phenotypes from baseline and physiological features.

### 7.2 Temporal Dynamics of Visceral Pain

At the group level, capsaicin exposure elicited a consistent biphasic pain response, characterized by rapid onset and gradual resolution. The median time to pain onset was 1.0 minute, while median time to relief was 5.0 minutes, which reflects a clear temporal dissociation between the initial rise in pain and the subsequent resolution phase.

This temporal pattern is consistent with the known pharmacology of TRPV1 activation and desensitization. The rapid onset is compatible with immediate nociceptor activation upon capsaicin exposure, while the gradual resolution may involve calcium-dependent desensitization processes and activation of descending inhibitory pathways.

Rank-based change-point detection (PELT algorithm) provided data-driven temporal landmarks, with the majority of change points clustering around minute 5, corresponding to the transition from the ascending to the descending phase of pain. This finding supports the interpretation that capsaicin-induced pain follows a structured temporal pattern rather than random fluctuation.

### 7.3 Heterogeneity of Pain Response Phenotypes

Clustering analyses revealed that individual responses are heterogeneous and can be classified into distinct temporal phenotypes, including delayed-peak, early-sustained, and late-rising patterns. Importantly, fuzzy clustering and shapelet analysis further demonstrated that these patterns form a continuum rather than discrete categories, driven by localized temporal dynamics rather than simple differences in peak intensity.

The identification of these phenotypes has important implications, as different temporal patterns may reflect differences in nociceptive activation, desensitization, symptom reporting, or attentional modulation; however, their biological correlates require validation using autonomic, neuroimaging, or molecular measures. These findings align with recent work on FGID subtyping, which has identified distinct patient clusters through nonlinear clustering of symptom severity profiles [22].

### 7.4 Predictability of Temporal Phenotypes from Baseline Characteristics

To evaluate whether temporal pain phenotypes could be anticipated from pre-experiment characteristics, we attempted to predict cluster membership using baseline demographic, questionnaire, ECG, and EGG data. In the observed dataset, random forest achieved the strongest performance among the evaluated baseline/physiology models, but its accuracy (0.495) and balanced accuracy (0.498) remained modest. Gradient boosting and stacking performed similarly or lower, and more complex models did not produce a clear improvement. For a three-class problem, chance-level balanced accuracy is 0.333.

This weak observed-data finding carries several implications. First, it suggests that the temporal phenotypes identified by DTW-based clustering are not simply reflections of pre-existing demographic, dietary, autonomic, or gastrointestinal electrical differences as currently measured. Second, the inability of more complex models to produce substantial performance gains suggests that the limitation lies mainly in the available predictive signal rather than in model capacity. Third, temporal phenotyping therefore provides information that is complementary to static participant characteristics and physiological state measures.

### 7.5 Symptom–Region Organization and Visceral Mapping

Symptom-based analyses showed that capsaicin-induced sensations are not randomly distributed but exhibit structured spatial–symptom coupling, with the right hypochondrium acting as a central hub. The right hypochondrium exhibited the highest weighted degree (368) in the symptom-region network, followed by the hypogastrium (267) and abdominal distension (240).

This centralized sensory organization is consistent with the expected physiological response to capsaicin stimulation, which primarily activates TRPV1-expressing afferents in the esophagus and stomach. The convergence of multiple high-weight edges onto the right hypochondrium supports the presence of a structured upper-abdominal sensory axis.

The spatial clustering of symptom expression has implications for understanding visceral afferent organization and may inform region-aware symptom assessment in future studies.

### 7.6 Relationship to FGID Frameworks

The Rome IV-informed mapping should be interpreted as a symptom-based alignment rather than a diagnostic classification. Because the present experimental protocol did not assess chronicity, symptom frequency over months, exclusion of structural disease, or clinical impairment, the observed biliary pain-like, bloating/distension-like, and IBS-like profiles indicate phenomenological overlap with Rome IV constructs rather than formal FGID diagnoses.

Main observations include that biliary pain-like, functional abdominal bloating/distension-like, and IBS-like patterns were the most frequent aligned categories. The aim of Rome IV-informed mapping was not to diagnose FGIDs, but to evaluate whether experimentally induced symptom patterns resemble clinically recognized symptom constructs.

### 7.7 Predictability of Short-Term Symptom Dynamics

The prediction analysis should be regarded as exploratory. Although logistic regression outperformed baseline models for short-term VAS direction prediction (balanced accuracy = 0.711, macro F1 = 0.687), the magnitude of performance indicates modest local predictability rather than immediate clinical applicability. Its main value is to show that the recovery phase of capsaicin-induced pain contains temporal information that can be modeled prospectively.

These results indicate that short-term recovery transitions contain measurable temporal structure, although external validation and clinically meaningful prediction targets are required before translational use. The predictive analysis was designed to test whether local temporal structure exists in VAS trajectories, rather than to develop a deployable clinical prediction model, consistent with broader cautions about clinical machine-learning use-case alignment [45-47].

### 7.8 Methodological Implications

This study shows the utility of combining time-series, clustering, and network approaches for characterizing complex physiological data. Main methodological contributions include DTW-based modeling for physiological data with variable temporal alignment, multi-layer integration (symptom–region–disease) for broad pattern analysis, shapelet analysis for interpretable feature extraction from clustering results, and group-wise cross-validation to prevent information leakage in repeated measures.

### 7.9 Clinical and Translational Relevance

The proposed multilayer analytical framework, linking temporal dynamics, symptom expression, and clinical mapping, provides a scalable approach for describing inter-individual variability and may inform future stratification studies. Although the oral capsaicin model provides a controlled and reproducible method for inducing upper gastrointestinal discomfort, it remains an acute experimental model and should not be considered equivalent to chronic FGIDs.

### 7.10 Limitations

Several limitations should be acknowledged. First, the acute capsaicin-induced model may not fully capture the complexity of chronic functional gastrointestinal disorders, limiting direct generalizability to clinical populations; the Rome IV-informed mapping represents symptom-based alignment rather than formal clinical diagnosis, as it does not incorporate chronicity, symptom frequency, or exclusion of organic disease. Second, the analysis remained primarily exploratory and descriptive, with clustering results sensitive to methodological choices and the stability of identified patterns across independent datasets remaining to be established. Third, the self-reported VAS measurements are inherently subjective, and the study did not incorporate multimodal physiological or neurobiological measures that could provide additional mechanistic insight into the observed pain dynamics.

### 7.11 Future Directions

Future research should integrate neuroimaging and autonomic data to provide mechanistic insight into pain dynamics, extend to intervention studies to evaluate treatment effects on temporal phenotypes, develop predictive models for symptom trajectories in clinical settings, refine FGID mapping frameworks to incorporate temporal criteria and dynamic symptom data, and conduct external validation in independent cohorts to establish generalizability. The identified clusters should be interpreted as data-driven temporal phenotypes whose stability requires validation in independent samples.

## Data Availability Statement

The datasets generated and/or analyzed during the current study are available from the corresponding author on reasonable request. The analysis code used in this study is available at [GitHub repository URL].

## References

[1] Sperber AD, Bangdiwala SI, Drossman DA, et al. Worldwide prevalence and burden of functional gastrointestinal disorders, results of Rome Foundation global study. *Gastroenterology*. 2021;160(1):99–114.

[2] Ford AC, Sperber AD, Corsetti M, Camilleri M. Irritable bowel syndrome. *Lancet*. 2020;396(10263):1675–1688.

[3] Cervero F, Laird JMA. Visceral pain. *Lancet*. 1999;353(9170):2145–2148.

[4] Sikandar S, Dickenson AH. Visceral pain: the ins and outs, the ups and downs. *Curr Opin Support Palliat Care*. 2012;6(1):17–26.

[5] Hammer J, Vogelsang H. Characterization of sensations induced by capsaicin in the upper gastrointestinal tract. *Neurogastroenterol Motil*. 2007;19(4):279–287.

[6] Bortolotti M, Porta S. Effect of red pepper on symptoms of irritable bowel syndrome: preliminary study. *Dig Dis Sci*. 2011;56(11):3288–3295.

[7] Caterina MJ, Schumacher MA, Tominaga M, et al. The capsaicin receptor: a heat-activated ion channel in the pain pathway. *Nature*. 1997;389(6653):816–824.

[8] Holzer P. TRPV1 and the gut: from a tasty receptor for a painful vanilloid to a key player in hyperalgesia. *Eur J Pharmacol*. 2004;500(1-3):231–241.

[9] Szallasi A, Blumberg PM. Vanilloid (capsaicin) receptors and mechanisms. *Pharmacol Rev*. 1999;51(2):159–212.

[10] Brederson JD, Kym PR, Szallasi A. Targeting TRP channels for pain relief. *Eur J Pharmacol*. 2013;716(1-3):61–76.

[11] Geppetti P, Nassini R, Materazzi S, Benemei S. The concept of neurogenic inflammation. *BJU Int*. 2008;101 Suppl 3:2–6.

[12] Vyklický L, Nováková-Toušová I, Benedikt J, et al. Calcium-dependent desensitization of vanilloid receptor TRPV1. *Physiol Res*. 2008;57 Suppl 3:S115–S126.

[13] Singh Tahim A, Santha P, Nagy I. Inflammatory mediators convert anandamide into a potent activator of the vanilloid type 1 transient receptor potential receptor. *Neuroscience*. 2005;136(2):539–548.

[14] Hammer J. Characterization of a reproducible gastric pain model using oral capsaicin titration in healthy volunteers. *Neurogastroenterol Motil*. 2011;23(9):e399–e406.

[15] Esmaillzadeh A, Keshteli AH, Hajishafiee M, et al. Consumption of spicy foods and the prevalence of irritable bowel syndrome. *World J Gastroenterol*. 2013;19(38):6465–6471.

[16] Reyes-Escogido ML, Gonzalez-Mondragon EG, Vazquez-Tzompantzi E. Chemical and pharmacological aspects of capsaicin. *Molecules*. 2011;16(2):1253–1270.

[17] Führer M, Hammer J. Effect of repeated, long-term capsaicin ingestion on intestinal chemo- and mechanosensation in healthy volunteers. *Neurogastroenterol Motil*. 2009;21(5):521.

[18] McCarty MF, DiNicolantonio JJ, O'Keefe JH. Capsaicin may have important potential for promoting vascular and metabolic health. *Open Heart*. 2015;2(1):e000262.

[19] Sharma SK, Vij AS, Sharma M. Mechanisms and clinical uses of capsaicin. *Eur J Pharmacol*. 2013;720(1-3):55–62.

[20] Akbar A, Yiangou Y, Facer P, et al. Increased capsaicin receptor TRPV1-expressing sensory fibres in irritable bowel syndrome and their correlation with abdominal pain. *Gut*. 2008;57(7):923–929.

[21] Farré R, Tack J. Food and symptom generation in functional gastrointestinal disorders: physiological aspects. *Am J Gastroenterol*. 2013;108(5):698–706.

[22] Feinle-Bisset C, Horowitz M. Dietary factors in functional dyspepsia. *Neurogastroenterol Motil*. 2006;18(8):608–618.

[23] Burns JW, Gerhart JI, Bruehl S, et al. Temporal dynamics of pain: an application of regime-switching models to ecological momentary assessment in chronic low back pain. *Pain*. 2018;159(5):968–976.

[24] Fillingim RB, Loeser JD, Baron R, Edwards RR. Assessment of chronic pain: domains, methods, and mechanisms. *J Pain*. 2016;17(9 Suppl):T10–T20.

[25] Drossman DA. Functional gastrointestinal disorders: history, pathophysiology, clinical features and Rome IV. *Gastroenterology*. 2016;150(6):1262–1279.

[26] Aziz Q, Fass R, Gyawali CP, et al. Functional esophageal disorders. *Gastroenterology*. 2016;150(6):1368–1379.

[27] Bellala G, Ganesan A, Krishna R, Saxman P, Scott C, Silveira M, et al. The nested structure of cancer symptoms. *Methods Inf Med*. 2010;49(6):581–591.

[28] Zhu Z, Hu H, Wu B, Hu Y. Editorial: Mapping symptom networks among co-occurrence of psychological and somatic symptoms. *Front Public Health*. 2023;11:1210151.

[29] Drossman DA, Hasler WL. Rome IV—Functional GI disorders: disorders of gut–brain interaction. *Gastroenterology*. 2016;150(6):1257–1261.

[30] Schmulson MJ, Drossman DA. What is new in Rome IV. *J Neurogastroenterol Motil*. 2017;23(2):151–163.

[31] Park SY, Bae H, Jeong HY, Lee JY, Kwon YK, Kim CE, et al. Identifying novel subtypes of functional gastrointestinal disorder by analyzing nonlinear structure in integrative biopsychosocial questionnaire data. *J Clin Med*. 2024;13(10):2821.

[32] Dunckley P, Wise RG, Fairhurst M, Hobden P, Aziz Q, Chang L, et al. A comparison of visceral and somatic pain processing in the human brainstem using functional magnetic resonance imaging. *J Neurosci*. 2005;25(32):7333–7341.

[33] Vermeulen W, De Man JG, Pelckmans PA, De Winter BY. Neuroanatomy of lower gastrointestinal pain disorders. *World J Gastroenterol*. 2014;20(4):1005–1020.

[34] Petitjean F, Ketterlin A, Gançarski P. A global averaging method for dynamic time warping, with applications to clustering. *Pattern Recognit*. 2011;44(3):678–693.

[35] Lai C-P, Chung P-CJ, Tseng H-C. Incremental fuzzy C medoids clustering of time series data using dynamic time warping distance. *PLoS One*. 2018;13(5):e0197344.

[36] Bezdek JC. *Pattern Recognition with Fuzzy Objective Function Algorithms*. New York: Plenum Press; 1981.

[37] Killick R, Fearnhead P, Eckley IA. Optimal detection of changepoints with a linear computational cost. *J Am Stat Assoc*. 2012;107(500):1590–1598.

[38] Ye L, Keogh E. Time series shapelets: a new primitive for data mining. *Proceedings of the 15th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*. 2009:947–956.

[39] Zhou X, Menche J, Barabási AL, Sharma A. Human symptoms–disease network. *Nat Commun*. 2014;5:4212.

[40] Hidalgo CA, Blumm N, Barabási AL, Christakis NA. A dynamic network approach for the study of human phenotypes. *PLoS Comput Biol*. 2009;5(4):e1000353.

[41] Goh KI, Cusick ME, Valle D, et al. The human disease network. *Proc Natl Acad Sci USA*. 2007;104(21):8685–8690.

[42] Black CJ, Ford AC. Global burden of irritable bowel syndrome: trends, predictions and risk factors. *Nat Rev Gastroenterol Hepatol*. 2020;17(8):473–486.

[43] Schmulson MJ, Drossman DA. What is new in Rome IV. *J Neurogastroenterol Motil*. 2017;23(2):151–163.

[44] Lacy BE, Mearin F, Chang L, Chey WD, Lembo AJ, Simren M, et al. Bowel disorders. *Gastroenterology*. 2016;150(6):1393–1407.e5.

[45] Lee CH, Yoon H-J. Medical big data: promise and challenges. *Kidney Res Clin Pract*. 2017;36(1):3–11.

[46] Buchlak QD, Esmaili N, Leveque JC, et al. Machine learning-based prediction of clinical pain using multimodal neuroimaging and autonomic metrics. *Pain Rep*. 2019;4(1):e698.

[47] Saeb S, Lonini L, Jayaraman A, et al. The need to approximate the use-case in clinical machine learning. *Gigascience*. 2017;6(5):1–9.
