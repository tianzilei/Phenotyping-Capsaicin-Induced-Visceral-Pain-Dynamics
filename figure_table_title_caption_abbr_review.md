# Figure/Table Title-Caption-Abbreviation Review

Review mode: `manuscript-writing` skill, document audit only.  
Scope checked: [MANUSCRIPT.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md), [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md), exported figures under [data/figures](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/data/figures), and compiled tables in [data/metrics/all_tables.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/data/metrics/all_tables.md).

Assumption: the target journal expects figure legends and table footnotes to be interpretable on a stand-alone basis.

## Must Fix First

### 1. Figure 12 and main-text Figure 2D use undeclared Rome-category abbreviations

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:133), [MANUSCRIPT.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md:153)
- **Issue:** The heatmap axis uses `FABD-like`, `IBS-like`, `FC/DD-like`, `CNVS`, `FD-PDS-like`, and `Unspecified FGI`, but the legend does not expand them.
- **Why it matters:** This is the most obvious stand-alone readability problem in the set. A reviewer can understand the main story, but not the exact category meanings.
- **Suggested action:** Add a legend sentence or footnote that expands every Rome-category abbreviation shown on the axis. `Unspecified FGI` is especially risky because the manuscript elsewhere uses `FGID`, so readers may assume a different meaning.

### 2. Figure 13 uses node abbreviations without a key

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:169)
- **Issue:** The Sankey node labels use shortened forms such as `Abd Pain`, `R-Hypo`, `Hypo`, `L-Hypo`, and `R-Lumb`, but the legend only explains `Other` nodes and `n (%) | flow`.
- **Why it matters:** The figure is dense, so readers rely on label compression. Without a key, the compression becomes a decoding task.
- **Suggested action:** Add one legend sentence defining all shortened symptom and region labels, and clarify that `No Match` means no Rome IV-informed category met the rule-based mapping threshold.

### 3. Figure 10 does not define the internal annotation symbols

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:109)
- **Issue:** The figure panels display `AUC`, `d`, and `t=... min`, but the legend does not explain them. It also does not explain the meaning of the solid segment, dashed trajectory, or shaded window.
- **Why it matters:** The graphic is analytically interesting, but the legend is too short for a non-author to decode the panel annotations.
- **Suggested action:** State what `AUC` and `d` represent, what `t` marks, and what each visual layer means.

### 4. Figure 16 title is semantically inconsistent with the manuscript description

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:211), [MANUSCRIPT.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md:171)
- **Issue:** The manuscript describes this panel as a complementary phenotype-classification confusion matrix, but the exported figure title reads `ECG/EGG Confusion Matrix`.
- **Why it matters:** The current title sounds narrower than the actual model input space and could mislead readers into thinking the classifier used only ECG/EGG variables.
- **Suggested action:** Rename the internal figure title so it matches the manuscript language, for example as a phenotype-classification confusion matrix from the complementary baseline-plus-physiology model.

### 5. Figure 15 contains multiple undeclared abbreviations

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:201)
- **Issue:** The y-axis includes `CCEI`, `AES`, `ECG`, `EGG`, `HR`, and `SQI`, but the legend does not define them.
- **Why it matters:** This panel is meant to be read variable-by-variable; undefined abbreviations block that.
- **Suggested action:** Add a short abbreviation footnote in the legend. The prose at [supplementary_latest.md:207](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:207) already helps, but it still does not close all abbreviations.

### 6. Table S3 is not yet self-contained

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:191)
- **Issue:** `SD`, `Macro F1`, `Weighted F1`, and the model label `PersistenceDir` are not defined in the table itself.
- **Why it matters:** `PersistenceDir` is a code-facing label, not a manuscript-facing one, and `F1` metrics should be expanded at least once in the table footnote.
- **Suggested action:** Rename `PersistenceDir` to the manuscript label used in Figure 14 (`persistence-direction` or `persistence-direction model`) and add a table footnote defining the metric abbreviations.

## Should Fix In The Same Pass

### 7. Figure 1 caption needs abbreviation closure

- **Location:** [MANUSCRIPT.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md:139)
- **Issue:** `VAS`, `SEM`, `DTW`, and `PELT` appear in the caption or panel text without legend-level definition.
- **Why it matters:** This is the opening composite figure, so it sets the standard for the rest of the paper.
- **Suggested action:** Add one closing abbreviation sentence to the caption.

### 8. Figure 3 caption is too short for the abbreviations visible in panels B-D

- **Location:** [MANUSCRIPT.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md:171)
- **Issue:** `VAS`, `ECG`, and `EGG` appear in the caption and figure panels, but are not defined there. Panel D also inherits the Figure 16 title inconsistency.
- **Why it matters:** Because Figure 3 is composite, readers may not open the supplementary counterparts first.
- **Suggested action:** Add an abbreviation sentence and align the wording of panel D with Figure 16 after that figure title is corrected.

### 9. Figure 5 needs model-label cleanup

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:51)
- **Issue:** The panel includes `MLP`, while the legend does not define it.
- **Why it matters:** Most other model labels are readable as ordinary words; `MLP` is the one abbreviation likely to interrupt comprehension.
- **Suggested action:** Either spell it out on the figure or define it in the legend.

### 10. Figure 7 needs feature-abbreviation definitions

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:73)
- **Issue:** The panel uses `HR`, `SDNN`, `LF/HF`, and `Normogastria %` without legend-level explanation.
- **Why it matters:** This is a feature-distribution figure, so the reader needs to know what each feature name means.
- **Suggested action:** Add a legend footnote that defines the ECG/EGG feature abbreviations shown on the axis.

### 11. Figure 8 legend should define `VAS` and `PELT`

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:85)
- **Issue:** The figure uses the threshold label `VAS > 3` and the method label `PELT`, but the legend does not define them.
- **Why it matters:** The figure is otherwise simple; this is a quick fix that makes it fully stand alone.
- **Suggested action:** Add a brief definition sentence in the legend.

### 12. Figure 14 and Table S3 should use the same model terminology

- **Location:** [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:179)
- **Issue:** Figure 14 uses the manuscript-friendly wording `persistence-direction`, but Table S3 uses `PersistenceDir`.
- **Why it matters:** Inconsistent model naming makes the figure-table pair look machine-exported rather than publication-edited.
- **Suggested action:** Standardize the label across the figure, table, and text.

## Lower-Priority Style/Consistency Issues

### 13. `Caption` in the main text and `Legend` in the supplement are not standardized

- **Location:** [MANUSCRIPT.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md:143), [supplementary_latest.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/supplementary_latest.md:41)
- **Issue:** Main-text figures use `Caption:` while supplementary figures use `Legend:`.
- **Why it matters:** This is minor, but standardizing the label makes the package feel more finished.
- **Suggested action:** Use one convention consistently, preferably whatever the target journal asks for.

### 14. Some figure titles in the manuscript and exported images are not fully aligned

- **Examples:** Figure 5 (`Baseline and physiological phenotype prediction` vs `Baseline/Physiology Phenotype Prediction`), Figure 6 (`Age distribution by temporal phenotype` vs `Age by Phenotype`), Figure 13, and especially Figure 16.
- **Why it matters:** Minor wording drift is acceptable, but larger drift can create uncertainty about whether the panel and the cited description are truly the same object.
- **Suggested action:** Harmonize manuscript titles and embedded image titles during the same figure-export pass.

## Passed Or Largely Acceptable

- **Table 1:** The title is clear and the abbreviation line is present at [MANUSCRIPT.md:135](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/MANUSCRIPT.md:135). No major caption/abbreviation defect.
- **Table S1, Table S2, Table S4:** No critical abbreviation problem in the current titles or bodies.
- **Figure 6, Figure 9, Figure 11:** No major title/caption abbreviation defect beyond ordinary style polishing.

## Suggested Batch Fix Order

1. Fix Figure 12, Figure 13, Figure 10, Figure 16, Figure 15, and Table S3.
2. Then add abbreviation-closure sentences to Figures 1, 3, 5, 7, 8, and 14.
3. Finally standardize `Caption`/`Legend` wording and align embedded titles with manuscript titles.

## Needs Verification

- If the journal allows a single shared abbreviation list for all figure legends, some repeated legend-level expansions may be reduced.
- If Figures S2b and S2c from [data/metrics/all_tables.md](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/data/metrics/all_tables.md:63) will re-enter the supplementary package, they should receive the same title/footnote check before submission.
