# Graph and Ranking Sensitivity Evidence

This page maps the graph-parameter and ranking-term sensitivity claims in Section V-D to a focused, reproducible experiment. The study evaluates four frozen paper operating points; it does not rerun the design-space exploration or select a new monitor configuration.

The machine-readable protocol is [`configs/graph_sensitivity.json`](../configs/graph_sensitivity.json), the runner is [`scripts/run_graph_sensitivity.py`](../scripts/run_graph_sensitivity.py), and the generated evidence is under [`results/notebook_run/graph_sensitivity/`](../results/notebook_run/graph_sensitivity/).

## Result

The archived run reproduces the manuscript ranges at their stated precision:

| Study family | MCC | Benign FPR | Top-`k` Jaccard versus baseline |
|---|---:|---:|---:|
| Graph-parameter variations | 0.940–0.992 | 0.77%–1.71% | 37.9%–100.0% |
| Ranking-term removals | 0.798–0.992 | 0.77%–1.64% | 53.8%–100.0% |

These are extrema of mean `workload=ALL` cross-validation metrics, not confidence intervals. The graph range includes the shared baseline; the ranking range includes only the four removal variants, with baseline rows retained as references.

Endpoint provenance is explicit in `graph_sensitivity_claims.json`. In particular:

- B/SPECTRE with `tau_c=0.45` supplies the graph MCC minimum (`0.940191...`).
- A/RH with `tau_c=0.45` supplies the graph FPR maximum (`1.7106...%`) and overlap minimum (`37.93...%`).
- A/RH without alignment supplies the ranking MCC minimum (`0.798297...`).
- B/SPECTRE without edge stability supplies the ranking FPR maximum (`1.6366...%`) and overlap minimum (`53.846...%`).
- B/DROOP supplies the `0.77%` lower FPR endpoint.
- A/DROOP supplies the `0.992` upper MCC endpoint; removing edge stability preserves its baseline decision metrics.

The largest MCC reductions named in the manuscript also reproduce: removing centrality is worst for A/DROOP, and removing alignment is worst for A/RH. Varying `pi_min` preserves MCC and FPR exactly in all four fixed cases. No graph variant uses the sparse-graph fallback. When normalized importance scores tie at a top-`k` boundary, the runner rounds them to 9 decimal places and uses feature name as a variant-neutral lexical tie-break; the claim audit lists every affected variant. The coarser ordering key prevents last-bit BLAS/LAPACK differences from changing tie order while retaining the unrounded score in the evidence table.

## Frozen Operating Points

| Setup/event | Data view | `k` | `N` | Aggregation | `lambda_res` | Weights | `Q` | `p` | Folds |
|---|---|---:|---:|---|---:|---|---:|---:|---:|
| A/DROOP | DROOP adaptive | 15 | 1000 | median | 0.00 | inverse variance | 15 | 0.99 | 3 |
| A/RH | standard | 20 | 550 | median | 1.00 | uniform | 8 | 0.99 | 5 |
| B/DROOP | DROOP adaptive | 15 | 200 | median | 0.50 | inverse variance | 15 | 0.99 | 3 |
| B/SPECTRE | standard | 30 | 700 | median | 0.75 | uniform | 8 | 0.99 | 5 |

The standard A ranking uses the anomaly scenarios available for Setup A (DROOP and RH), the standard B ranking uses those available for Setup B (DROOP and SPECTRE), and each DROOP-adaptive ranking uses the BENIGN/DROOP-only augmented view. This matches the archived rank-before-fold workflow. Anomaly labels do not create graph edges, but anomaly-scenario score alignment is one term in feature ranking.

## One-at-a-Time Graph Protocol

The baseline is `tau_c=0.35` and `pi_min=0.50`. Graph learning uses eight workload-stratified benign subsamples, a 70% fraction, seed 123 for Setup A and 1132 for Setup B, and at most `4F` admitted edges per bootstrap.

- Vary `tau_c` over `{0.25, 0.35, 0.45}` with `pi_min=0.50`.
- Vary `pi_min` over `{0.375, 0.50, 0.625}` with `tau_c=0.35`.
- Do not form their Cartesian product.

The actual partial-dependence threshold is `d_min=max(0.08, 0.35*tau_c)`, giving `{0.0875, 0.1225, 0.1575}`. With eight bootstraps, the three stability thresholds require recurrence in at least three, four, or five subsamples.

## Ranking-Term Removal Protocol

The baseline structural coefficients are:

```text
centrality                 0.35
edge stability             0.25
conditional dependence     0.20
alignment                  0.20
```

Remove one term at a time and renormalize the other three coefficients to sum to one. The telemetry-cost denominator remains fixed. For DROOP, the altered coefficients apply only inside the structural score; the outer structural coefficient `0.30`, semantic-prior coefficient `2.20`, and semantic prior itself remain fixed. Normalized scores are rounded to 9 decimal places for ordering and ties are resolved lexically by feature name, so platform-level numerical noise or a removed term cannot re-enter through a secondary tie-break. This is a sensitivity-specific, variant-neutral tie policy. Archive equivalence requires the same complete ordinal ranking and selected-feature ranks after that policy, as well as numerically equivalent unrounded score columns and an identical top-`k` set.

Jaccard overlap is `|F_variant intersection F_baseline| / |F_variant union F_baseline|`, where both sets are top-`k` features for the same setup, event, and data view. It is not graph-edge overlap, full-rank correlation, lifecycle overlap, or an uncertainty interval.

## Evaluation Contract

For every variant, the runner:

1. selects the variant's top-`k` features;
2. fits benign normalization and configured feature weights on all benign rows;
3. forms non-overlapping blocks within each workload/scenario recording and discards incomplete tails;
4. reuses deterministic block-level stratified folds at that fixed operating point;
5. estimates the threshold from the training fold's benign block scores using the 0.99 quantile;
6. predicts anomaly when the score is greater than or equal to the threshold; and
7. averages the `workload=ALL` fold metrics arithmetically.

This preserves the paper's disclosed feature-discovery-before-cross-validation design. It does not estimate feature-selection uncertainty or generalization to a new platform.

The frozen `Q` value is recorded as operating-point metadata. Consistent with the manuscript's Table VI detection metrics, MCC and FPR here are evaluated from floating-point block scores; this sensitivity experiment does not rerun quantized detection.

## Evidence Map

| Question | Artifact |
|---|---|
| Did the run use the disclosed variants and operating points? | `protocol.json`, `selected_operating_points.json` |
| Did each generated baseline have unique edges, the frozen feature universe, an exact top-`k` cardinality, and finite metrics? | `run_manifest.json`, `graph_sensitivity_claims.json` |
| Is the independent run scientifically equivalent to the archived reference? | `archive_comparison.json` written by `scripts/reproduce.py sensitivity --verify` |
| Which fold/workload rows underlie a mean metric? | `graph_sensitivity_fold_results.csv` |
| Which variant produces each endpoint? | `graph_sensitivity_claims.json`, `graph_sensitivity_summary.csv` |
| Which features were selected and how was Jaccard computed? | `graph_sensitivity_selected_features.csv`, `graph_sensitivity_feature_ranks.csv` |
| Which edges were admitted or retained, and did fallback activate? | `graph_sensitivity_graph_edges.csv` |
| Which code, inputs, packages, and outputs were used? | `run_manifest.json` |

The CSV files are tracked through Git LFS, so GitHub code search may not index their contents. The generated `README.md`, JSON claim audit, and this normal-Git documentation page keep the numerical result and provenance discoverable.

## Reproduce

```bash
uv sync --frozen --no-dev
uv run --frozen python scripts/reproduce.py fetch-lfs --scope sensitivity
uv run --frozen python scripts/reproduce.py sensitivity \
  --verify --repeat --run-id reviewer-sensitivity
```

The runner enforces Python 3.11.15 and every direct package pin, validates the exact 78-file standard-DDR and 52-file derived-DROOP inventories, and records all input hashes plus the NumPy/BLAS/threadpool runtime. Candidate feature universes are frozen in `configs/graph_sensitivity_feature_universes.json`, so generation does not read the archived result it is meant to reproduce. Self-contained structural gates establish that a generated run is internally valid; the wrapper's identity-keyed comparison separately establishes archive equivalence. A dirty or mismatched-runtime development run is clearly marked and cannot be accepted as archival evidence.
