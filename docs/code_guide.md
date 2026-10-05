# Code guide

`run.py` and the installed `capsaicin` entry point expose environment checks, aggregate inventory, module status, a synthetic demo, wide-table validation, and the explicitly provisional VAS working-model runner. The default analysis plan is draft; use a versioned, locally frozen controlled-input configuration before inference.

| Location | Role |
| --- | --- |
| `src/capsaicin/contracts.py`, `qc.py`, `analysis.py` | Token-preserving ingestion and actual-adjacent descriptive QC |
| `src/capsaicin/privacy.py` | Restricted, non-overwriting random-ID export with explicit field selection |
| `src/capsaicin/science_completion.py` | Whole-subject recorded-code/finite-change statistics |
| `src/capsaicin/distributed_*.py` | Resampling, subject-level prediction and R task contracts |
| `src/capsaicin/ecg_*`, `egg_*`, `reanalysis_signals.py` | Candidate signal processing; scientific gates remain separate |
| `src/capsaicin/states.py`, `readiness.py`, `reference_validation.py` | Descriptive states and explicit readiness gates |
| `R/vas_models.R`, `fpca_followup.R`, `sparse_fpca.R` | Implemented working models and FPCA analyses |
| `R/interfaces.R` | Unimplemented interfaces that raise errors |
| `scripts/deidentify_data.py` | Private-input export CLI |
| `scripts/build_scientific_figures.py` | All final figures/tables rendered from public aggregates, no fitting |
| `scripts/verify_public_release.py` | Current-tree privacy, credential-pattern and aggregate-hash audit |
| `scripts/verify_repository_structure.py` | Current-tree writing boundaries and English comments/docstrings |
| `scripts/verify_public_history.py` | All reachable commits/objects, integrity and concurrent-ref checks |
| `tests/` | Synthetic tests only |
| `config/` | Historical method parameters and publication/format configurations |

Analytical scripts retain versioned run contracts. Some require private upstream manifests/registries, a new site-specific execution configuration and remote compute; they cannot recreate individual analyses from aggregates alone. Example network addresses use the documentation-only `192.0.2.*` range, not an operational cluster. Individual identity/session-adjudication scripts and active pointers were excluded. No placeholder private registry is supplied.

`config/modules.json` reports the current 18-module status. The historical M00–M09 interface inventory is preserved separately as `modules_legacy_20260918.json`; its dated state should not be used as the current execution report. The old `python -m analysis ...` pipeline and in-place repair scripts are retired.

Public rendering has its own versioned configuration. It verifies aggregate-source hashes and writes a fresh directory. It never contacts the historical Dask cluster. Full real-data verification is distinct and cannot be performed using the released aggregates alone.

See [code style and repository boundaries](code_style.md) for pinned formatters, contributor checks, and the separation of public methods from unpublished writing. The field summary is in [field contract](field_contract.md).
