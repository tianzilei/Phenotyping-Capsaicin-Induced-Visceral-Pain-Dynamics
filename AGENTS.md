# Publication repository rules

Read README.md, docs/analysis_plan.md and docs/decision_log.md before changing analysis behavior.

- This is an exploratory, results-informed reanalysis, not a preregistration.
- Preserve E/T, missing values and actual minutes. Never fill baseline VAS with zero or bridge missing minutes.
- Keep real individual data, pseudonymized copies, source paths, identity mappings and individual adjudications outside Git. Synthetic fixtures must be explicitly labelled.
- Never modify candidate inputs in place. Create new, versioned outputs and record input/configuration/code hashes and software versions.
- Freeze the estimand, scale, interval and parameters before new inference. Published historical parameters and format validity do not confer scientific readiness.
- Resample/split at subject level and fit every prediction preprocessing step inside training subjects.
- Keep interface_only/design_only estimators unavailable; no fabricated outputs or silent fallback.
- Ignore ._* files. Do not execute old repair/adjustment code without reviewing provenance and purpose.
- Run meaningful synthetic ingestion tests with `python3 -m unittest discover -s tests -v` in the project environment.
- Run `python3 scripts/verify_public_release.py` and `python3 scripts/verify_public_history.py` before publication. Keep old private history outside the active Git object store; report local cleanup and remote replacement separately. An ordinary deletion commit does not remove historical participant data.
