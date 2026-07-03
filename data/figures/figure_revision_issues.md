# Figure Revision Issues

This file is the working issue list for batch figure revisions.

Scope:
- Figures 1 to 16
- Consolidated from local visual review
- Consolidated from Open Design review
- Includes the re-check of the updated Figure 11

## Global Issues

### Priority A

- Titles are generally too large and too heavy for publication-style figures.
- Several nominal-category bar charts use multi-hue gradients that imply ordered meaning without encoding a real ordered variable.
- Long axis labels reduce readability in dense figures, especially Figures 8, 12, and 13.
- Some figures still feel presentation-oriented rather than paper-oriented because of large markers, large annotation boxes, or heavy fills.

### Priority B

- Legend dependence is higher than necessary in several figures.
- Color semantics are not fully consistent across the full figure set.
- Some confidence ribbons, shaded windows, or overlays are visually stronger than the core signal.

## Figure-by-Figure Issue List

### Figure 1. Group Mean VAS Trajectory

- Title is oversized relative to the plot area.
- Late-stage confidence band is visually bulky.
- Plot could be quieter overall.

### Figure 2. Phenotype-Specific VAS Trajectories

- Confidence ribbons overlap and create haze.
- Legend requires repeated eye travel.
- On-screen colors work, but grayscale robustness should be checked.

### Figure 3. Symptom Burden

- Multi-color gradient suggests continuous meaning for nominal categories.
- Title competes too strongly with the bars.
- Small-format reading would benefit from explicit values.

### Figure 4. Pain Region Burden

- Same non-semantic gradient issue as Figure 3.
- Rare-region bars are easy to miss visually.
- Low-frequency tail could be presented more cleanly.

### Figure 5. Early VAS Window Classification

- Uncertainty ribbon is too visually dominant at early windows.
- Point markers feel slightly slide-like rather than paper-like.

### Figure 6. Baseline/Physiology Phenotype Prediction

- Color treatment implies more meaning than it carries.
- Top-model differences are hard to judge without explicit values.
- Title weight can be reduced.

### Figure 7. Age by Phenotype

- Outliers stretch the y-axis and flatten the main distributions.
- Group differences are visually subtle.
- Raw-point visibility is limited.

### Figure 8. Standardized ECG/EGG Features

- X-axis feature labels are crowded and heavily rotated.
- Outliers dominate several feature panels.
- Legend is larger than necessary.
- Figure is too dense for fast scanning in one panel.

### Figure 9. Onset and Change-Point Timing

- Overlaid histograms produce strong occlusion.
- `PELT` visually overwhelms the other methods.
- Distribution-shape comparison is harder than necessary.

### Figure 10. Kaplan-Meier Event Curves

- Visually reads more like a line chart than a formal survival figure.
- Censor marks are absent.
- Confidence intervals are absent if methodologically expected.
- Title is too large.

### Figure 11. Cluster-Specific Shapelets

Status:
- Improved substantially after the latest update.

Issues still remaining:
- Shared y-axis label is missing; the response variable should be stated explicitly.
- The meaning of solid line, dashed line, and shaded window is still not fully self-explanatory inside the figure alone.
- Right-top metric/info boxes are still slightly too large and visually prominent.
- `d` is not self-explanatory unless defined clearly in the caption or main text.

Issues resolved compared with the earlier version:
- Vertical row labels were successfully replaced with horizontal row headers.
- Time-window labeling is clearer now.
- X-axis naming is much better after changing to post-capsaicin time.

### Figure 12. Symptom-Region Co-occurrence

- Low-count values collapse into near-black and hide secondary structure.
- Rotated region labels are slow to scan.
- Figure would benefit from better low-end palette separation.

### Figure 13. Symptom-Rome IV Co-occurrence

- Long Rome IV labels are the largest label-readability problem in the set.
- Rotated labels carry too much cognitive load.
- Strong cells are not annotated, so the viewer depends heavily on axis text.

### Figure 14. VAS Direction Classification

- X-axis labels are more slanted than necessary.
- Metric colors may drift semantically relative to other figures in the set.
- Direct values would help if reproduced at smaller size.

### Figure 15. Random Forest Feature Importance

- Long feature names make the left side visually heavy.
- Gradient implies more semantic meaning than necessary.
- Small-format readability would improve with explicit values.

### Figure 16. ECG/EGG Confusion Matrix

- Axis labels use `0/1/2` instead of phenotype names.
- Raw counts alone make class-specific performance less interpretable.
- Title can be shortened by moving model name to subtitle or caption.

## Highest-Priority Batch Fixes

### Must fix first

- Figure 16:
  Replace numeric class labels with phenotype names and add normalized percentages.
- Figure 13:
  Rework Rome IV axis labeling with abbreviations and caption key.
- Figure 12:
  Improve low-count palette separation and label readability.
- Figure 8:
  Reduce label density and split if necessary.
- Figure 9:
  Replace heavy overlay strategy with a lower-occlusion layout.

### Should fix in the same batch

- Figures 3, 4, 6, 15:
  Remove non-semantic categorical gradients.
- Figures 1, 5, 10:
  Reduce title size and tone down visually heavy fills.
- Figure 11:
  Add shared y-axis label, clarify line/shading semantics, shrink info boxes slightly.

## Suggested Revision Order

1. Fix semantic clarity problems:
   Figures 16, 13, 12, 11
2. Fix density and occlusion problems:
   Figures 8, 9, 2
3. Fix style consistency problems:
   Figures 3, 4, 6, 15, then titles across all figures

## Revision Tracking

- [ ] Figure 1 revised
- [ ] Figure 2 revised
- [ ] Figure 3 revised
- [ ] Figure 4 revised
- [ ] Figure 5 revised
- [ ] Figure 6 revised
- [ ] Figure 7 revised
- [ ] Figure 8 revised
- [ ] Figure 9 revised
- [ ] Figure 10 revised
- [ ] Figure 11 revised
- [ ] Figure 12 revised
- [ ] Figure 13 revised
- [ ] Figure 14 revised
- [ ] Figure 15 revised
- [ ] Figure 16 revised
