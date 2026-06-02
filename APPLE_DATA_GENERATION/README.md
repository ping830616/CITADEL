# Apple Data Generation Provenance

This folder preserves the Apple data-generation material used to support the
CITADEL supplemental limited-observability study. It was copied from
`ping830616/DICE` at commit `b5e382e` and is included here only to document how
the Apple telemetry views were collected and checked.

Included content:

- `data generation/docs/`: collection methodology, tier definitions, workload
  and stressor descriptions, and feature-map notes.
- `data generation/generate_dataset.py`: dataset construction entry point.
- `data generation/src/dice/`: macOS collectors and tier-specific parsers.
- `data generation/tools/`: dataset validation and release-snapshot helpers.
- `scripts/validate_env.py`: environment preflight helper.

Not included:

- Upstream notebooks.
- Analysis outputs.
- Released dataset payloads.
- Crash-pilot traces.
- Figure or paper-result bundles.

For CITADEL experiments, use the main notebook in `notebooks/`. This folder is
for Apple telemetry provenance only.
