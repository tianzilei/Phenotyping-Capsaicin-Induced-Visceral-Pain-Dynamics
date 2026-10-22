# Reproducibility

Three different tasks have different prerequisites:

1. **Format/QC demonstration:** Python ≥3.11 standard library, public synthetic fixture and `config/synthetic.json`. `run.py demo` creates a new ignored run. No real records or statistical fitting are used.
2. **Public aggregate rendering:** NumPy, pandas, Matplotlib and Pillow in the project Python environment. The public aggregate manifest and rendering configuration identify every input hash; no private data, R or Dask workers are needed. `python3 scripts/build_final_artifacts.py --output NEW_DIRECTORY` recreates the current four main/six supporting figures and three main/twenty supporting tables. Install `dependencies/requirements-rendering.txt` for the retained figure environment. The historical `build_scientific_figures.py` recreates the October 4 export (ten figures and 21 tables). It refuses an existing output and performs no fitting/inference. Fonts and metadata may change image/PDF bytes across systems; numeric table values should match.
3. **Controlled individual analysis:** verified private records, aliases/session/clock/unit/QC evidence, new locally frozen execution configurations, and the relevant Python/R/Dask environment. Aggregate files cannot substitute for individual records or independent reference labels. Keep derived individual outputs and mappings outside Git and preserve input/config/code/environment hashes for each new run.

The source analysis environment records Python 3.12.13, R 4.6.1 and the package locks under `dependencies/project-python312-20261003-v2.lock.txt`, `dependencies/r-runtime-20261003-v1.csv` and `renv.lock`. The public full suite was checked in the existing project environment; no historical repair code or real inference was run for this update. Installing locked dependencies is a separate environment setup step, not scientific validation.

Use `CAPSAICIN_DATA_LOCATIONS=/absolute/private/locations.json` or ignored `config/local.json` for private location configuration. Exact alias indices remain private. The public location template is inactive. Generalized addresses/paths in historical parameter files require adaptation and a new frozen execution manifest; public copies are not the original byte-identical configuration. The inventory records both hashes and transformations.

`docs/release_inventory.json` records the source revision and per-file original/published hashes, including uncommitted source work and the current artifact alignment. `docs/release_verification.json` records the October 5 pre-publication checks; `docs/publication_status.json` retains that publication phase and remote/fresh-clone receipt. Those dated receipts retain their original scope. The October 23 artifact comparison and test record is `docs/artifact_alignment_verification_20261023.json`; its Git publication receipt is recorded separately. The original private run manifests, input hashes, source snapshots and backups are retained outside Git. Their audit history is preserved; no old scientific output was overwritten.

Run both content and full-history audits before any publication:

```sh
python3 scripts/verify_public_release.py
python3 scripts/verify_public_history.py
```

The history audit checks all locally reachable commits and stored objects. These audits do not certify anonymity, consent, statistical coverage, remote retained copies, or external scientific validation. Read [data privacy](data_privacy.md) and [history cleanup](history_cleanup.md) with its result.

Contributor formatting and structure checks are documented in [code style](code_style.md). Public rendering writes figures, full-precision tables, and an artifact index; manuscript narratives and submission-planning files are excluded.

The current artifact configuration is `config/final_artifacts_20261023_v1.json`. It checks every reviewed aggregate/configuration input hash before and after rendering. The two retained plotting CSVs and seven GAMM reference curves under `data/aggregate_sources/20261023/` preserve the later plotting inputs. Final table exports derive recognition accuracy from Table S10, reference group sizes from the aggregate cluster summary, and rule definitions/counts from the static codebook and Table S2. The final Table S1 labels historical plans separately from completed bootstrap draws and validation repetitions. See [artifact alignment](artifact_alignment.md) for the complete numbering map.
