# Reproducibility

Three different tasks have different prerequisites:

1. **Format/QC demonstration:** Python ≥3.11 standard library, public synthetic fixture and `config/synthetic.json`. `run.py demo` creates a new ignored run. No real records or statistical fitting are used.
2. **Public aggregate rendering:** NumPy, pandas, Matplotlib and Pillow in the project Python environment. The public aggregate manifest and rendering configuration identify every input hash; no private data, R or Dask workers are needed. `build_scientific_figures.py --output NEW_DIRECTORY` recreates all 10 figures and 21 tables. It refuses an existing output and performs no fitting/inference. Fonts and metadata may change image/PDF bytes across systems; numeric table values should match.
3. **Controlled individual analysis:** verified private records, aliases/session/clock/unit/QC evidence, new locally frozen execution configurations, and the relevant Python/R/Dask environment. Aggregate files cannot substitute for individual records or independent reference labels. Keep derived individual outputs and mappings outside Git and preserve input/config/code/environment hashes for each new run.

The source analysis environment records Python 3.12.13, R 4.6.1 and the package locks under `dependencies/project-python312-20261003-v2.lock.txt`, `dependencies/r-runtime-20261003-v1.csv` and `renv.lock`. The public full suite was checked in the existing project environment; no historical repair code or real inference was run for this update. Installing locked dependencies is a separate environment setup step, not scientific validation.

Use `CAPSAICIN_DATA_LOCATIONS=/absolute/private/locations.json` or ignored `config/local.json` for private location configuration. Exact alias indices remain private. The public location template is inactive. Generalized addresses/paths in historical parameter files require adaptation and a new frozen execution manifest; public copies are not the original byte-identical configuration. The inventory records both hashes and transformations.

`docs/release_inventory.json` records the source revision and per-file original/published hashes, including uncommitted source work. `docs/release_verification.json` records the pre-publication audits and synthetic test/render outcome; `docs/publication_status.json` records the publication phase and remote/fresh-clone receipt. These dated records are not interchangeable. The original private run manifests, input hashes, source snapshots and backups are retained outside Git. Their audit history is preserved; no old scientific output was overwritten.

Run both content and full-history audits before any publication:

```sh
python3 scripts/verify_public_release.py
python3 scripts/verify_public_history.py
```

The history audit checks all locally reachable commits and stored objects. These audits do not certify anonymity, consent, statistical coverage, remote retained copies, or external scientific validation. Read [data privacy](data_privacy.md) and [history cleanup](history_cleanup.md) with its result.

Contributor formatting and structure checks are documented in [code style](code_style.md). Public rendering writes figures, full-precision tables, and an artifact index; manuscript narratives and submission-planning files are excluded.
