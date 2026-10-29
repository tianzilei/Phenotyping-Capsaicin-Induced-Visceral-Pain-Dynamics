# Method scope

The library supports exploratory analysis of repeated numerical ratings. An analysis must specify its population, time support, outcome scale and eligible observations before fitting.

| Domain | Implemented calculations |
| --- | --- |
| Observation support | Minute-specific counts, stopping markers and paired/common-observer decompositions |
| Finite changes | Complete-interval changes, rates and increasing/decreasing/unchanged proportions |
| Functional variation | Complete and sparse functional analyses, reconstruction and stability summaries |
| Working models | Gaussian additive mixed models and residual-correlation sensitivities |
| Grouping | Euclidean, fuzzy and time-warping methods; training-defined group recovery |
| Prediction | Participant-separated splits, nested model selection and explicit error weighting |
| Physiology | Measured-feature fixed effects, clustered covariance and multiplicity adjustment |

Observation-specific summaries, complete-trajectory summaries, retrospective reconstruction and future-rating prediction answer different questions. Specify denominators and weighting explicitly. Monte Carlo endpoint precision, sampling uncertainty and scientific validity are separate properties.

Clinical phenotype validation, instantaneous-derivative acceptance, physiological source specificity, causal interpretation and external predictive validation require evidence beyond this library. Interface-only estimators continue to raise errors.

Parameter files are implementation examples or historical method settings; they do not authorize access to controlled records. The supported entry points are listed in the [code guide](code_guide.md).
