# Figure 7 evidence

This directory is the committed paper-facing reference for Figure 7 and the
associated Section V-I false-positive-rate statement.

- `intel_workload_orders/intel_workload_order_run_results.csv` contains every
  displayed recording-block replicate.
- `intel_workload_orders/intel_workload_order_summary.csv` contains the plotted
  means and sample standard deviations.
- `intel_workload_orders/fig_intel_workload_order_variation.png` is the archived
  rendering for visual inspection.
- `figure7_claims.json` traces the paper's `0.58% +/- 0.82` and
  `0.83% +/- 1.00` values to exact summary cells and confirms their rounding.
- `evidence_manifest.json` binds the evidence to a clean source commit, all 26
  input hashes, source and environment hashes, the locked runtime, and two
  independently executed runs.
- `repeat_verification.json` records that all 166 scientific CSV outputs from
  those two complete runs agreed with no missing or unverified result.
- `provenance/` preserves both run receipts and both analyzer manifests so the
  clean-checkout, source-commit, input, runtime, and protocol assertions can be
  inspected directly rather than only through their summary.

Regenerate and compare the paper-facing scientific tables with:

```text
uv run --frozen python scripts/reproduce.py intel-orders \
  --verify --repeat --run-id reviewer-figure7
```

CSV values are the cross-machine comparison target. Raster bytes are not
required to be identical because font and rendering backends can differ; the
new PNG must exist and be nonempty, and it must be generated from the verified
tables by the archived analyzer.

The preserved inputs were collected separately. Consequently, this evidence
supports workload-order and distribution sensitivity, not the transient time
of a continuously observed physical workload switch.
