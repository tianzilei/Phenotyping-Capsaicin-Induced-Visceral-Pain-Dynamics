# Public repository rules

Read README.md and docs/code_guide.md before changing supported interfaces.

- Keep draft article prose, individual records, source signals, identity maps and personal source locations outside the public tree.
- Keep numerical observations, missing entries, E/T markers and actual minutes distinct. Do not invent baseline values or bridge missing intervals.
- Preserve existing aggregate numerical results unless a change is explicitly requested.
- New analyses require explicit inputs, a defined estimand and a new output directory. Record parameters and software versions.
- Resample and split by participant. Fit preprocessing only in training participants.
- Keep unavailable estimators unavailable; do not fabricate results or replace failed fits with successful ones.
- Synthetic examples must be labelled and must not contain real participant records.
- Keep the public method library independent of private run inventories and recovery protocols.
- Run meaningful synthetic tests, scripts/verify_repository_structure.py and scripts/verify_public_release.py for changes.
- Publication-tree cleanup does not authorize rewriting existing Git history or pushing remote changes.
- Ignore ._* files. Do not execute historical repair scripts.
