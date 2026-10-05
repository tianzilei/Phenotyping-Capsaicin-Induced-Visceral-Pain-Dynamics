# Code style and repository boundaries

Python code uses [Ruff](https://docs.astral.sh/ruff/formatter/) 0.16.10 with four-space indentation, double quotes, LF line endings, and an 88-column formatting target. R code uses [Air](https://posit-dev.github.io/air/) 0.12.0 with two-space indentation, LF line endings, and the same line-width target. Existing R assignment operators are preserved. Configuration lives in `pyproject.toml`, `air.toml`, and `.editorconfig`.

Comments and docstrings use English. Multilingual source labels, matching patterns, and input values retain their original meaning. Translation of such values is a data transformation and is outside a style change.

## Local checks

Install `requirements-dev.txt` in the project environment and install the pinned Air version. Run:

```sh
ruff format --check .
ruff check .
air format --check .
python3 scripts/verify_repository_structure.py
python3 -m unittest discover -s tests -v
python3 scripts/verify_public_release.py
python3 scripts/verify_public_history.py
```

The lint selection checks syntax, separate import statements, undefined names/exports, and unbound locals. Formatting and comment checks cover all public Python and R files. They do not replace numerical tests or scientific validation.

## Public structure

- `src/capsaicin/`: reusable analysis and data-contract modules.
- `R/`: statistical working models and unavailable estimator interfaces.
- `scripts/`: execution, diagnostics, validation, and aggregate-rendering entry points. Controlled-data tasks require private inputs and frozen local configurations.
- `tests/`: synthetic fixtures and regression tests.
- `config/`, `schemas/`, and `dependencies/`: method parameters, input contracts, and environment records.
- `docs/`: method and maintenance documentation.
- `data/`: reviewed aggregate sources, numerical tables, figures, and an artifact index.

Unpublished writing, submission plans, and manuscript drafts stay outside the public tree. The current-tree structure guard excludes those artifacts; historical verification records retain their dated scope. The aggregate renderer produces an artifact index without manuscript narrative or fixed interpretations.

The October 5, 2026 review compared Python abstract syntax trees (normalizing split import statements and docstring indentation) and R parsed expressions against private pre-edit copies. R comparison normalizes single-expression braces introduced by Air. Formatting preserves analytical expressions, runtime literals, and numerical parameters. Removal of narrative generation is recorded separately. The original inputs and prior run outputs were not modified.
