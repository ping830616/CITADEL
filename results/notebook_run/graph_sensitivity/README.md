# Graph and ranking sensitivity evidence

**Scientific claim check: PASS. Archival provenance: PASS.** The values below are calculated from the generated summary; the manuscript ranges are comparison targets only.

## Reproduced ranges

| Study family | MCC | Benign FPR | Baseline top-k Jaccard | Matches draft precision |
|---|---:|---:|---:|:---:|
| Graph parameters | 0.940–0.992 | 0.77%–1.71% | 37.9%–100.0% | yes |
| Ranking-term removals | 0.798–0.992 | 0.77%–1.64% | 53.8%–100.0% | yes |

Graph ranges include the shared baseline. Ranking ranges include only the four removal variants; their baseline rows are archived as references.

## Endpoint provenance

| Family / metric | Minimum source | Maximum source |
|---|---|---|
| Graph parameters / MCC | B_SPECTRE / tau_c_0.45 | A_DROOP / baseline; A_DROOP / pi_min_0.375; A_DROOP / pi_min_0.625 |
| Graph parameters / benign FPR | B_DROOP / baseline; B_DROOP / tau_c_0.25; B_DROOP / tau_c_0.45; B_DROOP / pi_min_0.375; B_DROOP / pi_min_0.625 | A_RH / tau_c_0.45 |
| Graph parameters / top-k Jaccard | A_RH / tau_c_0.45 | A_DROOP / baseline; A_DROOP / pi_min_0.375; A_DROOP / pi_min_0.625; A_RH / baseline; A_RH / pi_min_0.375; B_DROOP / baseline; B_DROOP / pi_min_0.375; B_DROOP / pi_min_0.625; B_SPECTRE / baseline; B_SPECTRE / pi_min_0.375; B_SPECTRE / pi_min_0.625 |
| Ranking-term removals / MCC | A_RH / remove_alignment | A_DROOP / remove_edge_stability |
| Ranking-term removals / benign FPR | B_DROOP / remove_centrality; B_DROOP / remove_edge_stability; B_DROOP / remove_conditional_dependence | B_SPECTRE / remove_edge_stability |
| Ranking-term removals / top-k Jaccard | B_SPECTRE / remove_edge_stability | B_DROOP / remove_centrality; B_DROOP / remove_edge_stability; B_DROOP / remove_conditional_dependence |

## Self-contained generation gates

| Case | Unique graph edges | Frozen feature universe | Top-k cardinality | Finite metrics |
|---|:---:|:---:|:---:|:---:|
| A_DROOP | yes | yes | yes | yes |
| A_RH | yes | yes | yes | yes |
| B_DROOP | yes | yes | yes | yes |
| B_SPECTRE | yes | yes | yes | yes |

Every generation gate must pass before the sensitivity outputs are accepted. Archive equivalence is checked separately by scripts/reproduce.py sensitivity --verify. No graph fallback is allowed. Primary-score ties at a top-k boundary are resolved with the protocol's variant-neutral rounded-score/lexical rule and listed in the claim audit.

## Files

- `graph_sensitivity_summary.csv`: one row per case and variant with mean global CV metrics and overlap counts.
- `graph_sensitivity_fold_results.csv`: fold and workload rows underlying every summary value.
- `graph_sensitivity_selected_features.csv`: one row per selected feature and variant.
- `graph_sensitivity_feature_ranks.csv`: complete feature rankings and term values.
- `graph_sensitivity_graph_edges.csv`: admitted graph-edge audit rows, including retention and fallback flags.
- `graph_sensitivity_claims.json`: machine-readable extrema, source rows, and pass/fail checks.
- `protocol.json`: exact one-at-a-time protocol copied into the evidence bundle.
- `selected_operating_points.json`: the four frozen Table VI configurations.
- `run_manifest.json`: code/data/output hashes, runtime versions, graph subsample hashes, and baseline validations.

## Reproduce

From the repository root, materialize Git LFS data and run:

```bash
git lfs pull --include='data/telemetry/processed/ddr_data/*.csv,results/notebook_run/droop_adaptive_data/*.csv' --exclude=''
uv python install 3.11.15
uv sync --frozen
export PYTHONHASHSEED=123 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export MPLBACKEND=Agg TZ=UTC
uv run --frozen python scripts/run_graph_sensitivity.py --output-root results/reproduced/direct-sensitivity/notebook_run/graph_sensitivity
```

The direct command requires a clean checkout for archival provenance. The notebook contains a matching display cell that explicitly permits a dirty development run because notebook autosave changes execution metadata; such a manifest is marked `DEVELOPMENT_DIRTY_WORKTREE` and must not replace the committed archival bundle.
