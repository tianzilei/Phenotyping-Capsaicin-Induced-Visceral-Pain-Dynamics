# Reproduction

## Public aggregate rendering

Install the package versions listed in `dependencies/requirements-rendering.txt`, then run:

```sh
python scripts/build_final_artifacts.py --output NEW_DIRECTORY
```

The default configuration is `config/aligned_artifacts_20261027_v1.json`. Its `inputs` list identifies allowed source files, `table_sources` maps output tables, and `native_pngs` maps retained images. The renderer refuses existing destinations and external input paths. Source CSVs are copied without numerical rounding. Editable SVG/PDF output is generated from retained aggregates. Output records describe versions, counts and plotting settings.

The 20261023 layout remains available through its configuration. Historical 20261004 files are retained as aggregate artifacts; the former private-bundle rendering launcher is retired.

## New numerical runs

Supply controlled individual inputs separately, preserve actual observation times and define eligibility before fitting. Keep all individual outputs outside the public repository. Record the complete configuration and software environment in a new output directory. Historical private run inventories and recovery journals are not required by the supported library APIs.

The `logical-stream-v2` rule serializes the complete logical seed tuple as canonical UTF-8 JSON, includes its byte length, pads to 32-bit boundaries and supplies the resulting unsigned words to NumPy SeedSequence. Task identity and replicate number determine streams independently of scheduling order. This rule changes future draws relative to earlier software; it does not recreate historical replicate streams. Retained aggregate estimates are unchanged.

Recorded dependency pins describe the original environments. A different Python or numerical-library version must be reported as a different execution environment. Resource telemetry is optional for numerical workers; an unavailable monitor is labelled explicitly. Running the R subprocess resource guard requires psutil.

## Checks

Run the synthetic tests and both current-tree publication checks from the README. Test fixtures must remain synthetic. Statistical equivalence checks compare numerical arrays, coefficients and output tables directly. No publication success is implied by a local test result.
