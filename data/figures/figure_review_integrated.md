# Figure Review Integrated

This document consolidates two sources:

- Local GPT visual review across all exported figures
- Open Design project review (`critique.md`) generated from the imported figure board

The goal is not to redesign the figures from scratch, but to identify the highest-value improvements for publication-quality scientific graphics.

## Overall Synthesis

### What is already strong

- The full set has a consistent visual language.
- Core stories are usually obvious within 1 to 3 seconds.
- The trajectory figures are the strongest part of the set and already communicate the phenotype logic well.
- Sorting and ordering choices in the bar charts are mostly effective.
- The confusion matrix and feature importance figures already surface the intended analytic result clearly.

### Cross-figure issues both reviews agree on

- Titles are generally too large and too heavy for paper figures.
- Several categorical bar charts use multicolor gradients that imply ordered meaning where none exists.
- Some axis labels are too long or too rotated, especially in Figures 8, 12, and 13.
- A few figures still feel more like slide graphics than publication graphics because of marker size, annotation scale, or decorative weight.
- Several figures depend too much on legends instead of direct labeling or more self-explanatory axes.

### Global priority ranking

1. Reduce title size and annotation scale across the whole set.
2. Remove non-semantic gradients from nominal-category bar charts.
3. Improve label readability in Figures 8, 12, and 13.
4. Replace numeric class ticks with phenotype names in Figure 16.
5. Reduce visual occlusion from overlapping fills, ribbons, and histograms in Figures 2, 5, and 9.

## Figure-by-Figure Integrated Review

### Figure 1. Group Mean VAS Trajectory

- Strengths:
  The single main story is very clear. The mean line is easy to follow, and the uncertainty band is understandable without extra explanation.
- Issues:
  The title is oversized relative to the data region. The late-stage confidence band gets visually heavy and starts competing with the line itself.
- Integrated recommendation:
  Reduce the title by one visual level, lower ribbon opacity, and keep the plot area cleaner. If needed, move any extra wording into the caption rather than the figure title.
- Priority:
  Medium

### Figure 2. Phenotype-Specific VAS Trajectories

- Strengths:
  This is one of the best figures in the set. The phenotype separation is clinically intuitive, and the three line shapes tell a strong story.
- Issues:
  Overlapping ribbons create haze in the middle time range. The legend forces the eye to travel back and forth. The on-screen palette works, but grayscale robustness is less certain.
- Integrated recommendation:
  Make ribbons lighter, consider direct end-of-line labels near minute 20, and if journal printing is a concern, add line-type differentiation or verify colorblind-safe contrast.
- Priority:
  Medium-high

### Figure 3. Symptom Burden

- Strengths:
  Sorting is effective and the highest-burden symptoms stand out immediately.
- Issues:
  The multicolor gradient suggests a continuous or ordered variable, but the categories are nominal. The title visually dominates the bars more than necessary.
- Integrated recommendation:
  Switch to a restrained single-color treatment with optional highlight on the top one or two items. Add end labels if the figure may be shown small.
- Priority:
  High

### Figure 4. Pain Region Burden

- Strengths:
  The main rank ordering is easy to read and the dominant regions are obvious.
- Issues:
  It has the same semantic-color problem as Figure 3. The long tail is visually weak, so very low-frequency regions are easy to overlook.
- Integrated recommendation:
  Use one neutral hue, add end labels, and consider visually grouping rare regions or making the low-value labels easier to inspect.
- Priority:
  High

### Figure 5. Early VAS Window Classification

- Strengths:
  The trend is clean and interpretable. The figure has a strong one-sentence takeaway.
- Issues:
  The ribbon is broad and visually heavy at short windows. The point markers are slightly presentation-like.
- Integrated recommendation:
  Soften the ribbon opacity, reduce marker emphasis, and consider a cleaner line-first treatment. Keep any CI explanation in the caption.
- Priority:
  Medium

### Figure 6. Baseline/Physiology Phenotype Prediction

- Strengths:
  Model ranking is immediately understandable.
- Issues:
  Again, the bar colors imply more meaning than they carry. The exact gap among the top models is hard to judge without values.
- Integrated recommendation:
  Use one main color, highlight only the best or benchmark models, and add explicit values at the bar ends.
- Priority:
  High

### Figure 7. Age by Phenotype

- Strengths:
  Compact and statistically conventional. It does not overcomplicate a simple comparison.
- Issues:
  A few outliers stretch the y-axis and flatten the core boxes. Subtle group differences are hard to see.
- Integrated recommendation:
  Overlay jittered raw points with low alpha, or use violin plus box if sample size supports it. If kept as boxplots only, annotate medians or sample size externally.
- Priority:
  Medium

### Figure 8. Standardized ECG/EGG Features

- Strengths:
  The structure is systematic and the across-phenotype comparison is useful.
- Issues:
  This is one of the densest figures in the set. Feature labels are crowded and heavily rotated. Outliers dominate some features. The legend is larger than it needs to be.
- Integrated recommendation:
  Split into ECG and EGG panels or separate figures, abbreviate or line-break feature names, shrink outlier markers, and reduce legend size. Ordering features by analytic importance would also help.
- Priority:
  Very high

### Figure 9. Onset and Change-Point Timing

- Strengths:
  The concept is valuable and method comparison is meaningful.
- Issues:
  The overlaid histograms create too much occlusion. `PELT` visually overwhelms the other methods, making shape comparison harder than it should be.
- Integrated recommendation:
  Replace the overlay with faceted small multiples, step histograms, or ridgeline/density representations. Add median reference lines if possible.
- Priority:
  Very high

### Figure 10. Kaplan-Meier Event Curves

- Strengths:
  The difference between onset and relief is very memorable and the figure makes an immediate impression.
- Issues:
  It reads visually closer to a standard line chart than a formal survival figure because censor marks and confidence intervals are absent. The title is also large.
- Integrated recommendation:
  If methodologically appropriate, add censor marks and CI bands. Move the legend outward if space allows, and reduce title scale.
- Priority:
  Medium-high

### Figure 11. Cluster-Specific Shapelets

- Strengths:
  The small-multiples structure is logical and the AUC boxes are helpful.
- Issues:
  Typography is too large across the title, subheads, row labels, and annotation blocks. The vertical phenotype labels consume valuable data space. The framing elements compete with the curves.
- Integrated recommendation:
  Shrink title and subtitles, move phenotype labels into a left strip or margin, and simplify annotation boxes so the shapelets themselves become the focal point.
- Priority:
  High

### Figure 12. Symptom-Region Co-occurrence

- Strengths:
  The matrix format is appropriate and the strongest co-occurrence cells are obvious.
- Issues:
  Low counts disappear into the dark low end of the palette. Rotated region labels slow reading.
- Integrated recommendation:
  Use a palette with more low-end differentiation, consider masking or visually separating zeros, and shorten or wrap x-axis labels. Annotating key cells would help.
- Priority:
  Very high

### Figure 13. Symptom-Rome IV Co-occurrence

- Strengths:
  The main hot spots are visible and the figure has clear analytic intent.
- Issues:
  This is the single worst label-readability problem in the set. Rome IV category names are too long, too rotated, and too dense for fast reading.
- Integrated recommendation:
  Abbreviate category names and provide a caption key, or redesign label layout with wrapped text. If retained as a heatmap, annotate strongest cells to reduce dependence on the axis labels.
- Priority:
  Very high

### Figure 14. VAS Direction Classification

- Strengths:
  Grouped comparison works well and the metric structure is easy to understand.
- Issues:
  Slanted x-axis labels are not ideal. The color logic is metric-based here, but visually overlaps with phenotype-like color usage elsewhere, creating semantic drift across the figure set.
- Integrated recommendation:
  Shorten model names or keep them horizontal, add direct values if reduction size is small, and adopt a more consistent cross-figure color logic for model-performance graphics.
- Priority:
  Medium

### Figure 15. Random Forest Feature Importance

- Strengths:
  Ranking is clear and the top variables are easy to identify.
- Issues:
  The left margin is visually heavy because of long variable names. The color gradient again implies stronger semantics than necessary.
- Integrated recommendation:
  Use a simpler monochrome treatment with selective highlight for the top predictors, rename displayed variables more compactly, and add numeric value labels for small-format legibility.
- Priority:
  High

### Figure 16. ECG/EGG Confusion Matrix

- Strengths:
  The matrix is readable, diagonal dominance is easy to spot, and the counts are legible.
- Issues:
  The axes use `0`, `1`, and `2` instead of phenotype names, which weakens interpretability immediately. Raw counts alone also make class-specific comparison less informative.
- Integrated recommendation:
  Replace numeric ticks with phenotype names, add row-normalized percentages or a normalized companion matrix, and shorten the title by moving model name to subtitle or caption.
- Priority:
  Very high

## Highest-Impact Action List

- Figure 16:
  Rename axes with phenotype labels and add normalized percentages.
- Figure 13:
  Rework Rome IV labels with abbreviation plus caption key.
- Figure 12:
  Improve low-count color separation and shorten region labels.
- Figure 8:
  Reduce label density and split into subpanels if possible.
- Figure 9:
  Replace overlaid histogram strategy with a lower-occlusion layout.
- Figures 3, 4, 6, 15:
  Remove non-semantic multi-hue gradients from nominal bar charts.
- Figures 1, 5, 10, 11:
  Tone down title and annotation scale for a more publication-oriented feel.

## Suggested Revision Order

1. Fix semantic and labeling errors first:
   Figures 16, 13, 12, 8
2. Fix chart-form issues that affect interpretation:
   Figures 9, 11, 10
3. Standardize visual language across the set:
   Figures 3, 4, 6, 15, then title sizing everywhere

## Files Referenced

- Source figures:
  [data/figures](/Users/zileitian/Desktop/Phenotyping%20Capsaicin-Induced%20Visceral%20Pain%20Dynamics/data/figures)
- Open Design review board:
  [review.html](/Users/zileitian/Documents/Codex/open-design/.od/projects/visceral-pain-figure-review-cf4e/review.html)
- Open Design critique source:
  [critique.md](/Users/zileitian/Documents/Codex/open-design/.od/projects/visceral-pain-figure-review-cf4e/critique.md)
