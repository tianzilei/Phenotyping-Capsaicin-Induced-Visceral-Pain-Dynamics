# Capsaicin response analysis

Python and R implementations for longitudinal sensation scores, functional trajectories, participant-level validation and exploratory physiological features. The public tree contains reusable methods, parameter examples, synthetic fixtures and aggregate figures/tables. Article drafts and individual records are kept separately.

## Start here

```sh
python run.py doctor
python run.py demo --output NEW_DIRECTORY
python run.py inventory
python run.py plan
```

The demo and input-format checks use the Python standard library. Install `requirements.txt` for the numerical methods and graphics; install `requirements-dev.txt` for developer checks.

## Aggregate output

The [current export](data/published/20261027/README.md) contains four main figures, six supporting figures, two main tables and 29 supporting tables. [Earlier exports](docs/artifact_alignment.md) retain their own numbering. Native PNGs and numerical estimates are retained; model identifiers use descriptive serial labels where needed.

```sh
python scripts/build_final_artifacts.py --output NEW_DIRECTORY
```

Rendering reads public aggregates and creates a new destination. It performs no fitting or resampling. Input paths are confined to the repository. Vector appearance may depend on package and font versions.

## Methods and interfaces

- [Code guide](docs/code_guide.md) maps methods to source modules.
- [Input fields](docs/field_contract.md) describe scores, missing entries and categorical markers.
- [Method scope](docs/analysis_plan.md) distinguishes implemented calculations and unavailable inference.
- [Reproduction](docs/reproducibility.md) describes public rendering and controlled analysis inputs.
- [Physiological models](docs/physiology_20261017.md) describe the standalone numerical API.
- [Data handling](docs/data_privacy.md) describes restricted records and export requirements.

Random streams use the `logical-stream-v2` rule documented in [reproduction](docs/reproducibility.md). New resampling runs use this rule; retained historical aggregate results were not recomputed. Legacy private-run scheduling, recovery and content-signature inventories are outside the supported public interface.

## Verify a change

```sh
python -m unittest discover -s tests -v
python scripts/verify_repository_structure.py
python scripts/verify_public_release.py
```

The publication checks cover the current tree. Existing Git history and remote refs are handled separately. See [maintenance scope](docs/history_cleanup.md).
