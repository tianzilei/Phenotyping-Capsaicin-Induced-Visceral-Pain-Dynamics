**Table S3. Performance of Short-Term Direction Prediction Models**

| Model                 | Accuracy (mean ± SD) | Balanced Accuracy | Macro F1      | Weighted F1   |
| --------------------- | -------------------- | ----------------- | ------------- | ------------- |
| Majority              | 0.717 ± 0.016        | 0.500 ± 0.000     | 0.418 ± 0.005 | 0.599 ± 0.021 |
| Persistence-direction | 0.579 ± 0.032        | 0.531 ± 0.025     | 0.523 ± 0.025 | 0.594 ± 0.031 |
| Logistic regression   | 0.659 ± 0.011        | 0.654 ± 0.016     | 0.626 ± 0.012 | 0.674 ± 0.010 |

Abbreviations: SD, standard deviation; F1, harmonic mean of precision and recall; Macro F1, unweighted mean of class-specific F1 scores; Weighted F1, support-weighted mean of class-specific F1 scores. The persistence-direction model predicts decrease when the current local slope is sufficiently negative and otherwise predicts non-decrease.
