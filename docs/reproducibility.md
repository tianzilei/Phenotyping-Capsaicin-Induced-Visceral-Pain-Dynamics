# Reproducibility

## Current aggregate export

Use Python 3.12.13 and `dependencies/requirements-rendering.txt`. Run `python3 scripts/build_final_artifacts.py --output NEW_DIRECTORY` to create four main figures, six supporting figures, two main tables and 29 supporting tables. No private data, R, remote cluster or model fitting is used. The builder refuses an existing destination and checks every reviewed input hash before and after rendering.

`config/aligned_artifacts_20261027_v1.json` defines all 31 table sources, ten native PNG sources, vector-rendering inputs and current numbering. CSV exports and native PNGs reproduce source bytes exactly. Editable SVG and PDF plots are rendered from the retained aggregates with the current identifiers and physiology labels; environment differences may change vector bytes. Per-file output hashes, configuration/code hashes, plot environment and font hash are recorded in the output manifests. Native images remain separate from vector rasterization in the metadata.

Historical exports remain reproducible. Add `--config config/final_artifacts_20261023_v1.json` for the October 23 layout and 3/20 tables. `scripts/build_scientific_figures.py` reproduces the earlier October 4 export. Historical completed budgets and the 18-module inventory retain their original table identities in those archives; current Table S1 describes analysis subsets.

## Controlled individual analysis

Verified private records, participant/session identity evidence, clocks, units, QC and a new locally frozen execution configuration are required. Keep all individual outputs and mappings outside Git. Preserve input/configuration/code/environment hashes for each run. Public historical parameters and format validation alone do not authorize inference or establish physiological validity.

The original environment records Python 3.12.13, R 4.6.1 and the locks under `dependencies/`. The separate October 17 inference environment, code, results and execution prerequisites are described in [physiological inference](physiology_20261017.md). The original 161-test and extension 54-test families remain separate, and no historical p/q field is overwritten.

Use `CAPSAICIN_DATA_LOCATIONS` or ignored `config/local.json` for private location configuration. Exact identities and individual adjudications remain private. Generalized public configurations require locally frozen execution paths; original and public hashes and transformations are recorded in `docs/release_inventory.json`.

## Verification and publication

Run `python3 -m unittest discover -s tests -v`, `python3 scripts/verify_repository_structure.py`, `python3 scripts/verify_public_release.py` and `python3 scripts/verify_public_history.py`, together with the pinned Ruff/Air checks in [code style](code_style.md).

[Final document verification](document_alignment_verification_20261029.json) records the October 29 alignment and local checks. [Earlier integration verification](artifact_alignment_verification_20261027.json) retains the October 27 checks. Measurement and extraction parameters are summarized in the [measurement contract](measurement_contract.md). The unchanged ten native PNGs and 31 CSVs were compared directly with the final documents and accompanying materials; this review did not rerun inference. `docs/release_inventory.json` preserves source/public hashes. Prior October 5 and October 23 publication receipts are historical evidence for their own revisions. This change is prepared as a local commit for a user-managed push; it does not claim a new remote CI result or server-side historical erasure. [Data privacy](data_privacy.md) and [history cleanup](history_cleanup.md) retain the applicable scope.
