# Contributor checks

Use four-space Python indentation and English comments/docstrings. Keep data labels and numerical expressions intact when formatting. Python configuration is in `pyproject.toml`; R formatting configuration is in `air.toml`.

```sh
python -m unittest discover -s tests -v
python scripts/verify_repository_structure.py
python scripts/verify_public_release.py
```

Run the formatters pinned in the development requirements when available. Numerical tests must assess the calculation or data contract, including failure and missing-observation behavior. Tests of retired private-run recovery protocols are removed with those interfaces.

Code, generic parameter contracts, synthetic examples and aggregate artifacts may be public. Draft prose and participant-level material remain outside the tree. Changes to random streams must use a new documented scheme and must not silently overwrite retained results.
