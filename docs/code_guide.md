# Code guide

| Location | Supported role |
| --- | --- |
| `run.py`, `src/capsaicin/cli.py` | Environment information, aggregate inventory, synthetic demo and wide-table validation |
| `contracts.py`, `qc.py`, `stopping.py` | Input tokens, observation counts and adjacent-time summaries |
| `analysis.py`, `R/vas_models.R` | Explicitly provisional working-model execution with local inputs |
| `completion.py`, `science_completion.py`, `variability.py` | Finite changes, fixed-effect sufficient statistics and variability calculations |
| `distributed_*.py` | Numerical task definitions, participant splits and logical resampling streams |
| `random_streams.py` | Versioned seed construction from explicit logical identifiers |
| `physiology.py` | Repeated-block fixed effects, CR1/CRV3, wild bootstrap, BY/BH and independent full-design covariance calculations |
| `ecg_*`, `egg_*`, `reanalysis_signals.py` | Candidate signal-processing functions |
| `fnirs_source_selection.py`, `acq_source_selection.py` | Explicit registry/path ownership and source selection |
| `reference_validation.py`, `readiness.py`, `states.py` | Reference-admission contracts and scientific readiness gates |
| `privacy.py`, `scripts/deidentify_data.py` | Restricted random-ID export to a separate destination |
| `final_figures.py`, `final_artifacts.py`, `aligned_artifacts.py` | Aggregate plotting and numbered table export |
| `scripts/build_final_artifacts.py` | Public aggregate rendering command |
| `scripts/verify_public_release.py`, `verify_repository_structure.py` | Current publication-tree checks |
| `R/`, remaining script helpers | Numerical functions and standalone statistical helpers |

Paths in the first column below `src/capsaicin/` refer to modules in that package. Standalone helpers expose functions; their former private-run scheduling commands are retired. Individual analysis inputs cannot be reconstructed from aggregate tables.

The provisional runner still requires a locally frozen execution configuration and an R installation. R interfaces marked unavailable remain unavailable. Use a fresh destination for every analysis or render.
