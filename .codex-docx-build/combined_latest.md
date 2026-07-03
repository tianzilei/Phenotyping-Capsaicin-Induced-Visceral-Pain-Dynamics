# Title page

**Title:** Temporal Dynamics and Phenotypic Heterogeneity in Oral Capsaicin-Induced Human Visceral Pain

**Authors:** Zilei Tian, PhD, Jianzhen Jiang, PhD, MD, Chongkai Luo, MS, Jingya Cao, PhD, MD, Xueping Yu, PhD, MD, Sijing Chen, MS, Jing Li, MS, Tao Yin, PhD, MD, and Fang Zeng, PhD, MD.

**Affiliations:** 1. Acupuncture and Tuina School, The 3rd Teaching Hospital, Chengdu University of Traditional Chinese Medicine, Chengdu, Sichuan, China; 2. Acupuncture and Brain Science Research Center, Chengdu University of Traditional Chinese Medicine, Chengdu, Sichuan, China; 3. Key Laboratory of Acupuncture for Senile Disease (Chengdu University of TCM), Ministry of Education, Chengdu, Sichuan, China; 4. Sichuan College of Traditional Chinese Medicine, Mianyang, Sichuan, China. Author-affiliation mapping: Zilei Tian (1,2); Jianzhen Jiang (1,2); Chongkai Luo (1,2); Jingya Cao (1,2); Xueping Yu (4); Sijing Chen (1); Jing Li (1); Tao Yin (1,2,3); Fang Zeng (1,2,3).

**Corresponding author:** Fang Zeng, Acupuncture and Tuina School, The 3rd Teaching Hospital, Chengdu University of Traditional Chinese Medicine, Chengdu, Sichuan, China. Email: zengfang@cdutcm.edu.cn.

**Text Word Count:** about 2,970 words, excluding title page, abstract, references, tables, and figure legends

**Guarantor of the article:** Fang Zeng.

**Specific author contributions:** Zilei Tian: Conceptualization, methodology, formal analysis, data curation, visualization, writing-original draft, and writing-review and editing. Jianzhen Jiang: Methodology, investigation, data curation, and writing-review and editing. Chongkai Luo: Investigation, data curation, validation, and writing-review and editing. Jingya Cao: Investigation, data curation, and writing-review and editing. Xueping Yu: Formal analysis, visualization, and writing-review and editing. Sijing Chen: Data curation, investigation, project administration, and writing-review and editing. Jing Li: Resources, validation, and writing-review and editing. Tao Yin: Methodology, supervision, validation, and writing-review and editing. Fang Zeng: Funding acquisition, resources, supervision, project administration, and writing-review and editing. All authors approved the final submitted draft.

**Financial support:** The authors declare that financial support was received for this work and/or its publication. This study was supported by the National Outstanding Youth Science Fund Project of National Natural Science Foundation of China (grant number 82225050), the National Natural Science Foundation of China (grant number 82205285), Sichuan Provincial Natural Science Foundation Youth Fund Project (grant number 2024NSFSC11860), China Scholarship Council (grant number 202408730003), and Sichuan Province Tianfu Qingcheng Program (grant number 600008241023). The funding bodies provided financial support for the study and/or its publication. No funder had a direct role in data collection, data analysis, data interpretation, or drafting of the manuscript beyond the contributions of the funded authors described in the author-contributions statement. Fang Zeng, the corresponding author, contributed to funding acquisition, supervision, project administration, resources, and writing-review and editing as an author-investigator.

**Potential competing interests:** None declared.

**Needs verification before submission**

- Replace the masked registry information with the public registration link or registry identifier.
- Insert the final public OSF link and the final public code repository link in the data-availability statement.
- Verify reference metadata for entries affected by source-draft encoding artifacts, especially references 22, 24, 34, 38, and 39.

## Abstract

**Objectives:** Oral capsaicin studies often summarize pain with static endpoints, leaving temporal response patterns and symptom heterogeneity underexamined. This study combined trajectory analysis, symptom-region mapping, and Rome IV-informed categorization to characterize heterogeneity in oral capsaicin-induced visceral pain.

**Methods:** In this experimental observational study, 216 participants rated pain for 20 minutes after oral capsaicin administration on a visual analog scale (VAS). Analyses included onset and change-point detection, Kaplan-Meier estimation, dynamic time warping clustering, shapelet extraction, symptom-region network analysis, Rome IV-informed mapping, grouped Sankey visualization of phenotype-to-symptom-region-Rome IV flow, early-window phenotype classification, next-step VAS direction prediction, and phenotype prediction from baseline demographic, questionnaire-derived, electrocardiographic, electrogastrographic, and coupling features.

**Results:** The cohort mean trajectory peaked at minute 4 (mean VAS 4.22) and then declined. Median threshold-defined onset was 1.0 minute; median relief was not reached within 20 minutes. Dynamic time warping clustering identified delayed-peak (n=58), early-sustained (n=84), and late-rising (n=74) phenotypes (silhouette score 0.299). Abdominal distension was the most frequent symptom (154/216, 71.3%), and the right hypochondrium was the dominant regional hub (140/216, 64.8%; weighted degree 368). Rome IV-informed mapping aligned mainly with biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like patterns. Early-window phenotype classification reached accuracy 0.828 by 8 minutes and 0.902 with the full 20-minute trajectory. Logistic regression achieved balanced accuracy of 0.654 and macro F1 of 0.626 for next-step VAS direction prediction, whereas baseline-feature phenotype prediction remained modest (best primary accuracy 0.601).

**Conclusions:** Within a standardized administration and observation protocol, oral capsaicin produced heterogeneous visceral pain trajectories with clear temporal structure and recoverable phenotypic organization. Across trajectory, symptom-region, and Rome IV-informed analyses, the model captured disorders-of-gut-brain-interaction-relevant symptom patterns that static pain summaries would miss. The early-window and short-horizon prediction results support the model as a controllable experimental platform for dynamic phenotyping and for future studies that aim to forecast intervention-related improvement trajectories.

**Keywords:** capsaicin, visceral pain, time-series clustering, network analysis, Rome IV

## Study highlights

**WHAT IS KNOWN**

- Oral capsaicin provides a controlled experimental model of upper gastrointestinal discomfort.
- Static pain summaries can miss temporal structure and inter-individual heterogeneity.

**WHAT IS NEW HERE**

- VAS trajectories separated into three temporal phenotypes.
- Symptom-region networks concentrated in the right hypochondrium and hypogastrium.
- Standardized provocation produced coherent temporal landmarks and recoverable phenotype structure within the study protocol.
- Early-window and next-step prediction results support feasible short-horizon response forecasting, although baseline-only prediction remained modest.

## Introduction

Visceral pain is common in gastroenterology, but many studies reduce it to peak scores, mean scores, or area under the curve. These endpoints compress onset, persistence, and recovery [1-6]. In functional gastrointestinal disorders (FGIDs), timing, symptom quality, and perceived anatomical distribution shape clinical interpretation [1,2,7-11].

The oral capsaicin model provokes upper gastrointestinal discomfort under controlled conditions. Capsaicin activates transient receptor potential vanilloid 1 (TRPV1) channels on gastrointestinal sensory afferents and can produce burning, cramping, nausea, and distension-like sensations that overlap with FGID complaints [12-19]. TRPV1 activation may be followed by calcium-dependent desensitization, so the model can track pain dynamics after provocation [20-23].

Prior capsaicin work rarely integrates time course, symptom quality, and anatomical distribution in a single analysis. Many studies still emphasize static pain summaries [14,24-27]. Symptom qualities and anatomical locations are often analyzed separately, and few reports link symptom patterns to Rome IV constructs [7,8,28-31]. Oral capsaicin responses therefore remain incompletely characterized with respect to trajectory shape, symptom-region co-occurrence, and symptom-pattern alignment.

This study used the oral capsaicin model to examine heterogeneity across time, symptom pattern, and anatomical distribution. We aimed to identify temporal response phenotypes using dynamic time warping (DTW)-based clustering, quantify symptom-region structure, map symptom patterns to Rome IV-informed categories, assess short-term predictability of VAS changes, and test whether early trajectories or baseline demographic, questionnaire-derived, electrocardiographic (ECG), electrogastrographic (EGG), and ECG-EGG coupling features predicted phenotype membership. We hypothesized a priori that oral capsaicin responses would show structured temporal heterogeneity and that early VAS trajectory features would improve classification beyond baseline features alone.

## Methods

### Ethics, registration, and reporting

The Medical Ethics Committee of the Affiliated Hospital of Chengdu University of Traditional Chinese Medicine approved the study under amendment approval No. 2024KL-044-02. All participants provided written informed consent, and the study followed the Declaration of Helsinki. The capsaicin substudy belonged to a broader registered project governed by the same amendment approval; the public registry identifier should be inserted before submission. Reporting followed STROBE where applicable, and TIDieR elements describe the capsaicin administration procedure.

### Study design and participants

This experimental observational study used an oral capsaicin-induced visceral pain model under controlled laboratory conditions at Chengdu University of Traditional Chinese Medicine, Chengdu, Sichuan, China. Recruitment and data collection occurred from May 1, 2024, to June 1, 2025. The broader registered project recruited university volunteers. Eligible participants provided written informed consent, completed the oral capsaicin session, and contributed at least one valid post-administration VAS measurement. Participants were excluded if they did not complete capsaicin administration or lacked valid post-administration VAS data.

The analysis included 216 participants. All completed capsaicin ingestion and provided VAS ratings during the 20-minute observation period. The cohort ranged from 18 to 38 years of age. For time-to-event analyses, participants with no reported pain, defined as VAS equal to 0 at all recorded time points, were retained as right-censored observations.

### Capsaicin administration

Research staff dissolved food-grade capsaicin (purity 98%; CAS No. 404-86-4; Ruimao Biotechnology Co., Ltd., Xi'an, China) in ethanol (96%, v/v; Spirytus Rektyfikowany, Polmos, Poland) to prepare a 1% (w/v) stock solution. For each administration, staff encapsulated 10 microliters of solution, equivalent to 1 mg capsaicin, in a gastro-soluble gelatin capsule (Xuanyu Plastic Products Factory, Taizhou, China). Trained staff administered the capsule orally with water under direct observation. The protocol used no personalization, titration, or modification. Staff monitored participants for 20 minutes and recorded pain intensity at 1-minute intervals with a visual analog scale (VAS).

### VAS numeric analysis

Primary VAS variables included minute-level pain intensity, pain onset time, pain relief time, total pain exposure quantified as area under the curve (AUC), first-order differences, local summary statistics, time-to-peak, and peak intensity. Values marked "E" (early completion, defined as the participant reporting no sensation for 2 consecutive minutes) or "T" (trial termination for any reason, including excessive pain intensity or other intolerable symptoms) were treated as censored; once either marker appeared, all later measurements for that participant were set to missing and excluded from downstream analyses. Each operation excluded missing values. No analysis interpolated post-termination values.

Three approaches defined pain onset: first VAS >=3, first VAS difference >=0.5 between consecutive minutes, and change-point detection using the PELT algorithm with a rank-based model and penalty of 0.5 [32]. Kaplan-Meier methods estimated time to pain onset and time to pain relief. The Greenwood estimator produced median survival times and 95% confidence intervals. Because onset and relief used different event definitions in the same participants, curves were treated as descriptive estimates without a direct log-rank comparison. The trapezoidal rule computed AUC; each time series also provided peak VAS and time-to-peak.

### Temporal clustering and shapelet analysis

Time-series clustering used DTW-based K-means clustering with DTW barycentric averaging centroids and DTW-based fuzzy c-medoids clustering (m=2), following established DTW and fuzzy objective-function approaches [33-35]. Silhouette analysis characterized separation for the three-cluster solution. Shapelet analysis identified discriminative local subsequences [36]. Shapelet extraction used DTW-based distance computation, a subsequence length of 5, and the top 3 shapelets per cluster; shapelets with correlation above 0.90 were removed as redundant.

### Symptom, Rome IV, and network analyses

Symptom variables included symptom categories coded A-L, anatomical regions coded 1-9, symptom-region co-occurrence pairs, and Rome IV-aligned FGID categories. Coded symptom and region entries were parsed at the character level, stripped of delimiters, mapped to predefined labels, and deduplicated within participant. A rule-based algorithm mapped participant-level symptom profiles to Rome IV-informed categories using required and supportive symptoms and anatomical regions. The mapping represented symptom-based alignment with Rome IV constructs, not formal clinical diagnosis.

A bipartite symptom-region network was constructed from all pairwise combinations between each participant's reported symptoms and anatomical regions. Repeated symptom-region pairs within a participant contributed one occurrence. Across the cohort, pairwise associations formed a weighted matrix in which each cell represented co-occurrence frequency. A tripartite network linked symptoms, anatomical regions, and Rome IV-informed categories through symptom-region, symptom-disease, and region-disease edges [37-39]. A grouped supplementary Sankey visualization summarized participant-level symptom-region co-occurrence flows across temporal phenotype, symptom, region, and each participant's top Rome IV-informed category; lower-frequency nodes were combined for readability. Network analyses used frequency counts, not probabilities.

### Prediction and classification

To test whether early post-capsaicin trajectories predicted final temporal phenotype membership, a subject-level classification task compared the baseline feature matrix alone with datasets augmented by the first 3, 5, 8, or 20 minutes of VAS data. Added early-window features included raw prefix VAS values and derived summaries: mean, minimum, maximum, last value, prefix area under the curve, range, slope, early delta, and within-prefix peak time. Candidate classifiers included regularized linear models, support vector machines, distance-based methods, tree ensembles, histogram-based gradient boosting, and Gaussian naive Bayes. Stratified ten-fold cross-validation generated strict out-of-fold accuracy, balanced accuracy, and F1 summaries.

Separately, a sliding-window framework predicted whether the next VAS score would decrease. The procedure segmented each participant's VAS series into overlapping windows of length 3. Predictors included recent VAS values, current VAS, local summary statistics, local slope, monotonicity indicators, normalized time index, distances from recent running maxima and minima, and causal subject-level summaries computed from observations available up to the current minute. Models included a majority classifier, a persistence-direction model, and class-balanced logistic regression. Group-wise cross-validation assessed accuracy, balanced accuracy, macro F1, and weighted F1 to prevent leakage from repeated measures.

To assess whether pre-experiment characteristics predicted temporal phenotypes, classifiers used baseline demographic and questionnaire-derived exposure-history and symptom features together with ECG, EGG, and ECG-EGG coupling features. Column medians imputed missing values. Six model architectures were evaluated: class-balanced logistic regression, class-balanced random forest, gradient boosting, histogram-based gradient boosting, multilayer perceptron with early stopping, and a stacking ensemble. Stratified ten-fold cross-validation used balanced accuracy and macro F1 as primary metrics. A complementary classifier family used the same encoded feature matrix to generate supplementary feature-importance and confusion-matrix summaries.

### Safety monitoring

Staff monitored adverse events throughout the post-administration observation period. The protocol defined an adverse event as any unfavorable or unintended medical occurrence that exceeded the expected transient gastrointestinal sensations induced by capsaicin, required medical intervention, led to trial termination, or caused clinically significant discomfort or risk. Each T-coded trial termination was classified as an adverse event. Staff recorded expected transient sensations, including heartburn, abdominal pain, abdominal distension, nausea, or related gastrointestinal discomfort, as study outcomes unless they exceeded the anticipated response profile.

## Results

### Participant characteristics

The analytic cohort included 216 participants. All completed capsaicin administration and contributed at least one valid post-administration VAS measurement. Core baseline variables were complete. Nine participants had T-coded adverse events that ended the trial early. No serious adverse events occurred. All symptoms resolved within 30 minutes, and no participant developed a more severe condition.

**Table 1. Baseline Characteristics of Study Participants (N=216)**

| Characteristic | Value |
|:--|:--|
| Age, years, mean +/- SD | 20.4 +/- 1.9 |
| Female, n (%) | 125 (57.9%) |
| Male, n (%) | 91 (42.1%) |
| Height, cm, mean +/- SD | 167.2 +/- 8.9 |
| Weight, kg, mean +/- SD | 60.3 +/- 12.0 |
| BMI, kg/m^2, mean +/- SD | 21.4 +/- 3.3 |
| Time since last meal, hours, mean +/- SD | 4.1 +/- 2.0 |
| Non-drinker, n (%) | 116 (53.7%) |
| Occasional drinker, n (%) | 83 (38.4%) |
| Regular drinker, n (%) | 17 (7.9%) |
| CCEI, mean +/- SD | 20.1 +/- 14.8 |
| AES, mean +/- SD | 5.3 +/- 6.8 |
| No baseline GI symptoms, n (%) | 148 (68.5%) |
| Mild baseline GI symptoms, n (%) | 56 (25.9%) |
| Moderate baseline GI symptoms, n (%) | 12 (5.6%) |

Abbreviations: AES, Acute Exposure Score; BMI, body mass index; CCEI, Chronic Capsaicin Exposure Index; GI, gastrointestinal; SD, standard deviation.

### Temporal VAS dynamics

**Figure 1. Temporal dynamics of oral capsaicin-induced visceral pain.**

![Figure 1. Temporal dynamics of oral capsaicin-induced visceral pain.](data/figures/figure1_temporal_dynamics_composite.png){width=6.0in}

*Caption:* Panel A shows the group-level mean VAS trajectory during the 20-minute observation period, with SEM uncertainty. Panel B shows mean VAS trajectories stratified by DTW-derived temporal phenotype. Panel C shows the distributions of threshold-defined onset, derivative-defined onset, and PELT-derived change-point timing. Panel D shows Kaplan-Meier curves for time to pain onset and time to pain relief. Abbreviations: VAS, visual analog scale; SEM, standard error of the mean; DTW, dynamic time warping; PELT, pruned exact linear time.

The cohort mean VAS trajectory rose during the first 4 minutes, peaked at 4.22 at minute 4, and then declined while remaining above zero throughout follow-up (Figure 1A). Median threshold-defined onset occurred at 1.0 minute. The modal PELT change point occurred at minute 5 (Figure 1C), and the Kaplan-Meier median relief time was not reached within 20 minutes because only 12 of 216 participants met the relief criterion (Figure 1D). Among participants with calculable values, mean participant-level AUC was 53.17 VAS-minutes.

### Temporal phenotypes

DTW-based clustering identified three temporal patterns: delayed-peak responders (n=58), early-sustained responders (n=84), and late-rising responders (n=74) (Figure 1B). The average silhouette score was 0.299, indicating moderate separation among overlapping classes. Fuzzy clustering and shapelet analysis were consistent with these phenotypes but did not support sharply separated subtypes.

### Symptoms, anatomical regions, and Rome IV-informed mapping

**Figure 2. Symptom and spatial burden of capsaicin-induced visceral pain.**

![Figure 2. Symptom and spatial burden of capsaicin-induced visceral pain.](data/figures/figure2_symptom_spatial_burden_composite.png){width=6.0in}

*Caption:* Panel A shows the ranked symptom burden across participants. Panel B shows the ranked burden of perceived anatomical regions. Panel C shows the symptom-region co-occurrence heatmap based on participant-level co-occurrence counts. Panel D shows the symptom-Rome IV-informed co-occurrence heatmap based on rule-mapped participant-level alignments. Abbreviations: CNVS, chronic nausea and vomiting syndrome; FABD-like, functional abdominal bloating/distension-like; FC/DD-like, functional constipation/defecatory disorder-like; FD-PDS-like, postprandial distress syndrome-like functional dyspepsia; IBS-like, irritable bowel syndrome-like; Unspecified FGI, unspecified functional gastrointestinal symptom pattern.

Across 216 participants, abdominal distension was the most frequent reported symptom (154/216, 71.3%), followed by nausea (85/216, 39.4%) and abdominal pain (84/216, 38.9%) (Figure 2A). The most frequently reported anatomical regions were the right hypochondrium (140/216, 64.8%) and hypogastrium (92/216, 42.6%) (Figure 2B).

Rome IV-informed mapping aligned mainly with biliary pain-like (57/216, 26.4%), functional abdominal bloating/distension-like (35/216, 16.2%), and irritable bowel syndrome-like (25/216, 11.6%) patterns (Figure 2D). These categories describe symptom-pattern alignment, not formal FGID diagnoses.

### Symptom-region network structure

The symptom-region frequency matrix showed a non-uniform spatial distribution (Figure 2C). The strongest co-occurrence edge linked abdominal distension with the right hypochondrium (weight=110), and the highest-intensity cells remained concentrated in the right hypochondrium and hypogastrium. The right hypochondrium had the highest weighted degree (368), followed by the hypogastrium (267).

The tripartite network centered on the right hypochondrium and hypogastrium and connected most strongly to biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like alignments. The grouped Sankey summary showed that all three temporal phenotypes converged onto overlapping symptom-region hubs, especially abdominal distension, nausea, abdominal pain, the right hypochondrium, and the hypogastrium, while `No Match` remained a common terminal Rome IV-informed state. Because the analysis expanded participant-level co-occurrence patterns, these findings describe recurrence rather than one-to-one anatomical localization.

### Prediction and classification

**Figure 3. Predictability of pain evolution and temporal phenotype.**

![Figure 3. Predictability of pain evolution and temporal phenotype.](data/figures/figure3_prediction_composite.png){width=6.0in}

*Caption:* Panel A shows subject-level temporal phenotype classification as progressively longer early VAS windows are included. Panel B shows phenotype prediction performance from baseline demographic, questionnaire-derived, ECG, EGG, and coupling features. Panel C shows model performance for predicting whether the next VAS value will decrease. Panel D shows the confusion matrix from the best complementary baseline-plus-physiology classifier, annotated with counts and row-normalized percentages. Abbreviations: VAS, visual analog scale; ECG, electrocardiographic; EGG, electrogastrographic.

Temporal phenotype classification improved as the early VAS window length increased (Figure 3A): accuracy was 0.615 without post-capsaicin trajectory information, 0.828 with an 8-minute window, and 0.902 with the full 20-minute trajectory.

Short-term direction prediction of the next VAS change was moderate (Figure 3C). Logistic regression achieved balanced accuracy of 0.654 +/- 0.016 and macro F1 of 0.626 +/- 0.012, outperforming the majority baseline in class-balanced performance. Recent trajectory history carried some information about entry into the recovery phase.

Prediction from baseline demographic and questionnaire-derived exposure-history and symptom features, together with ECG, EGG, and ECG-EGG coupling features, remained modest (Figure 3B). In the primary model set, histogram-based gradient boosting achieved the highest mean accuracy (0.601), while random forest achieved the highest mean balanced accuracy (0.610). The complementary confusion matrix also showed only partial separation across the three phenotypes (Figure 3D). The measured baseline and physiological features did not classify phenotype membership with high accuracy.

### Safety and adverse events

Nine participants (4.2%) experienced T-coded adverse events that ended the trial early. No serious adverse events occurred. All symptoms resolved within 30 minutes, and no participant developed a more severe condition.

## Discussion

Oral capsaicin responses were temporally patterned and heterogeneous. The cohort-level VAS trajectory was biphasic, with rapid onset and slower resolution (Figure 1A,D), whereas participant-level responses separated into three partly overlapping temporal phenotypes rather than a single dominant curve (Figure 1B). Symptom analyses added spatial and symptom-construct context: abdominal distension was common, the right hypochondrium was the dominant network hub, and Rome IV-informed mapping linked experimental symptom profiles to biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like constructs (Figure 2A-D). Static intensity summaries therefore provide an incomplete account of visceral pain across time, symptom quality, and perceived anatomical distribution [1-4,7,8].

The temporal findings support response-shape analysis alongside conventional static summaries. Median onset occurred within 1 minute, the main change point clustered around minute 5, and median relief was not reached during the 20-minute observation period (Figure 1C,D). Peak VAS and AUC would capture these features only partly, even though such endpoints remain common in experimental pain studies and broader pain assessment frameworks [24-27]. These results indicate that the oral capsaicin model can distinguish onset, persistence, and recovery as separate phases of the same response [26,27].

Taken together, the fixed administration protocol, early onset, concentrated change-point timing, and recoverable phenotype structure support the model as an experimentally controllable provocation paradigm with reproducible cohort-level temporal landmarks.

The observed early rise followed by slower decline is physiologically plausible in light of prior capsaicin and TRPV1 literature. Capsaicin activates TRPV1-expressing visceral afferents and can evoke burning, cramping, nausea, and distension-like sensations in the upper gastrointestinal tract [12,14-18]. Prior work also indicates that TRPV1 signaling is dynamic, with downstream modulation and calcium-dependent desensitization shaping responses after initial activation [15,16,20-22]. We did not test receptor-level mechanisms. The combination of rapid onset, delayed recovery, and between-subject variability is consistent with a time-dependent sensory process rather than a brief impulse-like event [17,24,25].

The clustering results argue against treating oral capsaicin pain as a single canonical curve. DTW preserved shape information when peak timing varied between participants, and fuzzy clustering showed that phenotype boundaries were not sharp (Figure 1B). The three phenotypes are best interpreted as recurring response patterns rather than fixed biological subtypes. That interpretation aligns with literature showing that pain and FGID-related symptom data often contain structured heterogeneity rather than one homogeneous presentation [2,7,8,26,31]. The labels delayed-peak, early-sustained, and late-rising are descriptive. The convergence of DTW clustering, fuzzy assignment, early-window classification, and shapelet-level local motifs nevertheless suggests that these patterns are not arbitrary analytic artifacts. Independent replication and stronger physiological anchoring are still needed before investigators treat them as disease entities.

Symptom-region mapping showed that capsaicin-induced sensations were unevenly distributed across anatomical regions. Figure 2A-C shows that abdominal distension, nausea, and abdominal pain clustered disproportionately in the right hypochondrium and hypogastrium rather than spreading evenly across the abdominal map. The supplementary Sankey view further shows that the temporal phenotypes did not branch into fully separate symptom repertoires; instead, they converged on shared symptom-region hubs and a small set of dominant Rome IV-informed endpoints, with a substantial `No Match` remainder that reflects the conservative rule-based mapping. This spatial concentration may inform region-aware symptom assessment, although it should not be read as an anatomical map of nociceptive origin. Network-based symptom analyses describe how complaints cluster across participants; they do not identify a single underlying organ source [29,30,37-39].

The Rome IV-informed categories require cautious interpretation. The mapping assessed symptom overlap with Rome IV constructs; it did not diagnose FGIDs or incorporate the chronicity requirements central to Rome IV classification [7,8,10,11]. The observed biliary pain-like, bloating/distension-like, and irritable bowel syndrome-like patterns in Figure 2D nevertheless show that an acute experimental provocation can generate symptom constellations resembling clinically recognized constructs at the level of phenomenology. The capsaicin model may help probe components of symptom generation that later become embedded in disorders of gut-brain interaction, while remaining distinct from patient diagnosis [7,8,10].

The prediction analyses separated trajectory information from pre-exposure information. Early VAS windows improved phenotype classification, indicating that trajectory shape became informative within the first minutes after exposure (Figure 3A). By 8 minutes, classification accuracy had increased to 0.828; by 20 minutes, phenotype membership was largely recoverable from the observed trajectory history, as expected because the clustering outcome was trajectory-derived. Baseline demographic and questionnaire-derived exposure-history and symptom features, together with ECG, EGG, and ECG-EGG coupling features, showed only modest discrimination (Figure 3B,D). In this experimental setting, the evolving pain signal contained more phenotype-specific information than the pre-exposure feature set. For intervention-oriented work, these findings support prospective short-horizon monitoring: the current signal was informative enough to anticipate near-term VAS direction and to identify emerging phenotype structure before the full trajectory was observed. The present study did not model treatment-related improvement directly, but it establishes a methodological basis for future models that predict intervention-associated change once interventional trajectories are available.

Several limitations frame the interpretation. First, the capsaicin model captures acute experimental discomfort rather than chronic disease, so translation to FGID populations is indirect. Second, VAS remains a subjective outcome, even when sampled densely. Third, cluster structure may shift with analytic choices, including distance metric, censoring rules, and cluster number. Fourth, the Rome IV-informed mapping was rule-based and symptom-limited and cannot substitute for formal clinical phenotyping. Fifth, the physiological feature set was insufficient for mechanistic inference. Sixth, the study did not assess between-session test-retest stability, so reliability at this stage should be understood as within-protocol structural coherence and recoverable temporal organization rather than demonstrated longitudinal reproducibility. T-coded adverse events were self-limited and no serious adverse events occurred, but early trial termination in a subset of participants indicates that tolerability remains part of the model's operating boundary.

Future studies should test phenotype stability in independent cohorts, add autonomic, neuroimaging, or molecular measures, refine symptom mapping with temporal criteria, and assess whether temporal response patterns predict patient outcomes or intervention response.

Within this protocol, the oral capsaicin model offered a controlled and analytically tractable way to study heterogeneous visceral pain dynamics. Trajectory analysis, symptom-region structure, and Rome IV-informed mapping pointed to DGBI-relevant symptom patterns rather than a nonspecific pain signal alone. The response patterns were coherent enough to support dynamic phenotyping, short-horizon forecasting, and the design of future studies that evaluate whether intervention-associated improvement can be predicted prospectively. The next step is to establish between-session stability, external replication, and stronger biological anchoring before the model is treated as a reliable surrogate of clinical disease [1,2,7,8,31].

## Author disclosures

### Ethics approval and consent to participate

The Medical Ethics Committee of the Affiliated Hospital of Chengdu University of Traditional Chinese Medicine approved the study under amendment approval No. 2024KL-044-02. All participants provided written informed consent.

### Funding

The authors declare that financial support was received for this work and/or its publication. This study was supported by the National Outstanding Youth Science Fund Project of National Natural Science Foundation of China (grant number 82225050), the National Natural Science Foundation of China (grant number 82205285), Sichuan Provincial Natural Science Foundation Youth Fund Project (grant number 2024NSFSC11860), China Scholarship Council (grant number 202408730003), and Sichuan Province Tianfu Qingcheng Program (grant number 600008241023). The funding bodies provided financial support for the study and/or its publication. No funder had a direct role in data collection, data analysis, data interpretation, or drafting of the manuscript beyond the contributions of the funded authors described in the author-contributions statement. Fang Zeng, the corresponding author, contributed to funding acquisition, supervision, project administration, resources, and writing-review and editing as an author-investigator.

### Competing interests

The authors declare that the research was conducted in the absence of any commercial or financial relationships that could be construed as a potential conflict of interest.

### Author contributions

ZT: Conceptualization, methodology, formal analysis, data curation, visualization, writing-original draft, and writing-review and editing. JJ: Methodology, investigation, data curation, and writing-review and editing. CL: Investigation, data curation, validation, and writing-review and editing. JC: Investigation, data curation, and writing-review and editing. XY: Formal analysis, visualization, and writing-review and editing. SC: Data curation, investigation, project administration, and writing-review and editing. JL: Resources, validation, and writing-review and editing. TY: Methodology, supervision, validation, and writing-review and editing. FZ: Funding acquisition, resources, supervision, project administration, and writing-review and editing. All authors approved the final submitted draft.

### AI assistance disclosure

The authors declare that no generative artificial intelligence or AI-assisted technologies were used in the writing of this manuscript, the production of images or graphical elements, or the collection and analysis of data.

### Acknowledgments

The authors gratefully acknowledge support from the National Natural Science Foundation of China and thank all participants and staff involved in the trial for their valuable contributions.

## Data availability statement

The electrocardiographic and electrogastrographic datasets generated and/or analyzed during the current study will be made publicly available through the Open Science Framework (OSF). The analysis code will be made publicly available through the project's GitHub repository. The final public OSF link and the final public code repository link should be inserted before submission.

## Supplementary material

Detailed supplementary methods and results are provided in the accompanying Supplementary Appendix. The final supplementary package will retain Supplementary Methods S1-S2, Figures S1-S5, and Tables S1-S4, which provide expanded early-window classification details, baseline-plus-physiology summaries, shapelet motifs, symptom-region and Rome IV-informed network summaries, short-term direction-prediction metrics, complementary feature-importance diagnostics, and adverse-event tabulations that extend but do not duplicate the main-text composite figures and Table 1.

## References

[1] Sperber AD, Bangdiwala SI, Drossman DA, et al. Worldwide prevalence and burden of functional gastrointestinal disorders, results of Rome Foundation global study. *Gastroenterology*. 2021;160(1):99-114.

[2] Ford AC, Sperber AD, Corsetti M, Camilleri M. Irritable bowel syndrome. *Lancet*. 2020;396(10263):1675-1688.

[3] Cervero F, Laird JMA. Visceral pain. *Lancet*. 1999;353(9170):2145-2148.

[4] Sikandar S, Dickenson AH. Visceral pain: the ins and outs, the ups and downs. *Curr Opin Support Palliat Care*. 2012;6(1):17-26.

[5] Dunckley P, Wise RG, Fairhurst M, Hobden P, Aziz Q, Chang L, et al. A comparison of visceral and somatic pain processing in the human brainstem using functional magnetic resonance imaging. *J Neurosci*. 2005;25(32):7333-7341.

[6] Vermeulen W, De Man JG, Pelckmans PA, De Winter BY. Neuroanatomy of lower gastrointestinal pain disorders. *World J Gastroenterol*. 2014;20(4):1005-1020.

[7] Drossman DA. Functional gastrointestinal disorders: history, pathophysiology, clinical features and Rome IV. *Gastroenterology*. 2016;150(6):1262-1279.

[8] Drossman DA, Hasler WL. Rome IV-functional GI disorders: disorders of gut-brain interaction. *Gastroenterology*. 2016;150(6):1257-1261.

[9] Black CJ, Ford AC. Global burden of irritable bowel syndrome: trends, predictions and risk factors. *Nat Rev Gastroenterol Hepatol*. 2020;17(8):473-486.

[10] Schmulson MJ, Drossman DA. What is new in Rome IV. *J Neurogastroenterol Motil*. 2017;23(2):151-163.

[11] Lacy BE, Mearin F, Chang L, Chey WD, Lembo AJ, Simren M, et al. Bowel disorders. *Gastroenterology*. 2016;150(6):1393-1407.e5.

[12] Hammer J, Vogelsang H. Characterization of sensations induced by capsaicin in the upper gastrointestinal tract. *Neurogastroenterol Motil*. 2007;19(4):279-287.

[13] Bortolotti M, Porta S. Effect of red pepper on symptoms of irritable bowel syndrome: preliminary study. *Dig Dis Sci*. 2011;56(11):3288-3295.

[14] Caterina MJ, Schumacher MA, Tominaga M, et al. The capsaicin receptor: a heat-activated ion channel in the pain pathway. *Nature*. 1997;389(6653):816-824.

[15] Holzer P. TRPV1 and the gut: from a tasty receptor for a painful vanilloid to a key player in hyperalgesia. *Eur J Pharmacol*. 2004;500(1-3):231-241.

[16] Szallasi A, Blumberg PM. Vanilloid (capsaicin) receptors and mechanisms. *Pharmacol Rev*. 1999;51(2):159-212.

[17] Hammer J. Characterization of a reproducible gastric pain model using oral capsaicin titration in healthy volunteers. *Neurogastroenterol Motil*. 2011;23(9):e399-e406.

[18] Reyes-Escogido ML, Gonzalez-Mondragon EG, Vazquez-Tzompantzi E. Chemical and pharmacological aspects of capsaicin. *Molecules*. 2011;16(2):1253-1270.

[19] Akbar A, Yiangou Y, Facer P, et al. Increased capsaicin receptor TRPV1-expressing sensory fibres in irritable bowel syndrome and their correlation with abdominal pain. *Gut*. 2008;57(7):923-929.

[20] Brederson JD, Kym PR, Szallasi A. Targeting TRP channels for pain relief. *Eur J Pharmacol*. 2013;716(1-3):61-76.

[21] Geppetti P, Nassini R, Materazzi S, Benemei S. The concept of neurogenic inflammation. *BJU Int*. 2008;101 Suppl 3:2-6.

[22] Vyklicky L, Novakova-Tousova K, Benedikt J, et al. Calcium-dependent desensitization of vanilloid receptor TRPV1. *Physiol Res*. 2008;57 Suppl 3:S115-S126.

[23] Singh Tahim A, Santha P, Nagy I. Inflammatory mediators convert anandamide into a potent activator of the vanilloid type 1 transient receptor potential receptor. *Neuroscience*. 2005;136(2):539-548.

[24] Farre R, Tack J. Food and symptom generation in functional gastrointestinal disorders: physiological aspects. *Am J Gastroenterol*. 2013;108(5):698-706.

[25] Feinle-Bisset C, Horowitz M. Dietary factors in functional dyspepsia. *Neurogastroenterol Motil*. 2006;18(8):608-618.

[26] Burns JW, Gerhart JI, Bruehl S, et al. Temporal dynamics of pain: an application of regime-switching models to ecological momentary assessment in chronic low back pain. *Pain*. 2018;159(5):968-976.

[27] Fillingim RB, Loeser JD, Baron R, Edwards RR. Assessment of chronic pain: domains, methods, and mechanisms. *J Pain*. 2016;17(9 Suppl):T10-T20.

[28] Aziz Q, Fass R, Gyawali CP, et al. Functional esophageal disorders. *Gastroenterology*. 2016;150(6):1368-1379.

[29] Bellala G, Ganesan A, Krishna R, Saxman P, Scott C, Silveira M, et al. The nested structure of cancer symptoms. *Methods Inf Med*. 2010;49(6):581-591.

[30] Zhu Z, Hu H, Wu B, Hu Y. Editorial: Mapping symptom networks among co-occurrence of psychological and somatic symptoms. *Front Public Health*. 2023;11:1210151.

[31] Park SY, Bae H, Jeong HY, Lee JY, Kwon YK, Kim CE, et al. Identifying novel subtypes of functional gastrointestinal disorder by analyzing nonlinear structure in integrative biopsychosocial questionnaire data. *J Clin Med*. 2024;13(10):2821.

[32] Killick R, Fearnhead P, Eckley IA. Optimal detection of changepoints with a linear computational cost. *J Am Stat Assoc*. 2012;107(500):1590-1598.

[33] Petitjean F, Ketterlin A, Gancarski P. A global averaging method for dynamic time warping, with applications to clustering. *Pattern Recognit*. 2011;44(3):678-693.

[34] Lai C-P, Chung P-CJ, Tseng H-C. Incremental fuzzy C medoids clustering of time series data using dynamic time warping distance. *PLoS One*. 2018;13(5):e0197344.

[35] Bezdek JC. *Pattern Recognition with Fuzzy Objective Function Algorithms*. New York: Plenum Press; 1981.

[36] Ye L, Keogh E. Time series shapelets: a new primitive for data mining. *Proceedings of the 15th ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*. 2009:947-956.

[37] Zhou X, Menche J, Barabasi AL, Sharma A. Human symptoms-disease network. *Nat Commun*. 2014;5:4212.

[38] Hidalgo CA, Blumm N, Barabasi AL, Christakis NA. A dynamic network approach for the study of human phenotypes. *PLoS Comput Biol*. 2009;5(4):e1000353.

[39] Goh KI, Cusick ME, Valle D, et al. The human disease network. *Proc Natl Acad Sci USA*. 2007;104(21):8685-8690.

\newpage

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

![Figure S1. Age by Phenotype.](data/figures/figure7_age_by_phenotype.png){width=6.0in}

*Caption:* Age distributions stratified by temporal phenotype.

Age distributions overlapped across delayed-peak, early-sustained, and late-rising phenotypes.

This matched the broader baseline-prediction result: age alone did not organize the time-based phenotypes identified here.

**Figure S2. Standardized ECG/EGG Feature Distributions.**

![Figure S2. Standardized ECG/EGG Feature Distributions.](data/figures/figure8_ecg_egg_features.png){width=6.0in}

*Caption:* Standardized ECG and EGG feature distributions across temporal phenotypes. Abbreviations: ECG, electrocardiographic; EGG, electrogastrographic; HR, heart rate; SDNN, standard deviation of normal-to-normal intervals; LF/HF, low-frequency/high-frequency power ratio.

Feature distributions showed partial between-cluster differences with substantial overlap.

Visual separation in a subset of features did not translate into strong multivariable phenotype classification, indicating that the available physiological feature set was insufficient to recover the temporal phenotypes with high accuracy.

### S4. Local temporal motifs

**Figure S3. Cluster-specific shapelets.**

![Figure S3. Cluster-specific shapelets.](data/figures/figure11_shapelets.png){width=6.0in}

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

![Figure S4. Temporal phenotype to symptom-region-Rome IV flow structure.](data/figures/figure14_network_sankey.png){width=6.0in}

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

![Figure S5. Complementary Phenotype-Classification Random Forest Feature Importance.](data/figures/figure15_ecg_feature_importance.png){width=6.0in}

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

