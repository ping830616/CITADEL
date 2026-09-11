# TCAD End-To-End Result Methodology

This document is the start-to-finish runbook for turning the CITADEL repository into the result section of the TCAD paper. It explains what to run, where each result comes from, which figures and tables should appear in the manuscript, and how to combine MacBook notebook results with ASU/Linux Vivado hardware results.

The short version is:

`immutable commit -> locked notebook and sensitivity runs -> isolated result bundles -> ASU Vivado RTL/FPGA -> manifest-backed comparison -> final TCAD evidence`.

## 1. Goal

The TCAD paper should show that CITADEL is more than an offline anomaly detector. The result section should support five claims:

1. CITADEL detects SLM-relevant anomalies with strong block-level metrics.
2. CITADEL keeps the runtime feature set compact through stable conditional telemetry ranking.
3. The design-space sweep explains how feature budget, decision-block length, aggregation, weighting, and fixed-point precision affect accuracy and cost.
4. Fixed-point CINTAS is numerically stable enough for edge hardware.
5. The deployed detector can be checked and recalibrated when benign telemetry drifts.

The Apple observability study is useful, but it should remain supplemental. It supports portability and observability discussion; it should not be mixed into the main CINTAS area, power, or FPGA claims.

## 2. Main Artifacts

Use the end-to-end notebook as the primary entry point; it invokes the focused
graph/ranking sensitivity runner where appropriate:

```text
notebooks/exact_tcad_all_experiments.ipynb
```

Important output folders:

```text
results/notebook_run/tcad_ablation/
results/notebook_run/graph_sensitivity/
results/notebook_run/tcad_ablation/paper_figures/
results/notebook_run/lifecycle_drift/
results/notebook_run/fpga/
results/notebook_run/rtl_sweep/
results/reproduced/<unique-run-id>/
```

The `results/notebook_run/` paths above are archived references. Reviewer runs
write only to uniquely named directories below `results/reproduced/`.

Important source files:

```text
configs/tcad_grid_balanced.json
configs/tcad_grid_full.json
configs/graph_sensitivity.json
scripts/run_graph_sensitivity.py
docs/graph_ranking_sensitivity.md
rtl/cintas/cintas_stream.sv
hardware/cintas_operator_costs.csv
environment.yml
```

## 3. Machine Roles

Use the machines this way.

| Machine | Role | Why |
|---|---|---|
| MacBook M2 | Main notebook run, result inspection, figures, paper writing, final merge | Fast enough for notebook work and convenient for Overleaf/result review |
| ASU Linux server | Long notebook run if needed, Vivado synthesis and post-synthesis reporting | Better for remote long jobs and vendor FPGA tools |
| MacBook M2 with OSS CAD Suite | RTL lint, open-source synthesis checks, optional simulation workflow | Good for reproducible local hardware sanity checks |

Recommended final workflow:

1. Check out the same immutable artifact commit on MacBook and ASU.
2. Run the locked notebook launcher into a unique `results/reproduced/` root.
3. Run the strict Vivado launcher on ASU into another unique reproduced root.
4. Retain its plan, manifest, comparison report, parsed CSV, and raw reports.
5. Copy only the uniquely named reproduction bundle back to MacBook if needed.
6. Compare with the archived results; never overwrite an archived reference.

## 4. Full Notebook Procedure

From an immutable checkout, use the locked reviewer launcher:

```bash
uv python install 3.11.15
uv sync --frozen
uv run --frozen python scripts/reproduce.py fetch-lfs \
  --scope core --include-reference
uv run --frozen python scripts/reproduce.py notebook \
  --profile core --preset full --data-mode real \
  --verify --run-id reviewer-core
```

For interactive inspection, start Jupyter with the equivalent controls already
set in the process environment:

```bash
export CITADEL_SEED=123 CITADEL_THREADS=1 CITADEL_PROFILE=core
export CITADEL_DATA_MODE=real CITADEL_TCAD_PRESET=full
export CITADEL_RUN_LIFECYCLE=1
export CITADEL_RESULTS_ROOT=results/reproduced/reviewer-interactive/notebook_run
export CITADEL_STRICT_RUNTIME=1 PYTHONHASHSEED=123
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8
export MPLBACKEND=Agg MPLCONFIGDIR=/tmp/citadel-matplotlib
uv run --frozen python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

Repeated-run verification is implemented by `scripts/reproduce.py --repeat` so
the two executions use separate result roots; it is not a notebook Boolean.

Set `TCAD_PRESET = "full"` when reconstructing the paper-selected Table VI operating points. The shorter `balanced` grid is a development/revalidation grid and omits median aggregation, `N=550/700`, `k=20`, and `lambda_res=0/1`. The dedicated graph/ranking sensitivity runner is a separate focused experiment: it uses the frozen Table VI points and does not execute either DSE grid.

Run the notebook from top to bottom. The key paper sections are:

| Notebook Section | Purpose | Main Output |
|---|---|---|
| 4. Full Design-Space Sweep | Main CITADEL sweep | `tcad_ablation_summary.csv`, fold results, selected features |
| 5. Results Gallery | Selected operating points, frozen-point sensitivity, workload robustness, feature-budget trade-offs, graph interpretation, lifecycle results, and paper figures | gallery CSVs/figures plus `graph_sensitivity/` evidence |
| 6. Reproducibility Manifest Audit | Cross-artifact provenance check | manifest-audit display |
| 7. Supplemental Cost Artifact | Additional cost analysis | supplemental cost outputs |
| 8. RTL Workflow | Lint/simulation workflow | RTL validation outputs |
| 9. Export Fixed-Point Golden Vectors | RTL verification input | golden-vector CSV |
| 10. Merge RTL/FPGA Results | Hardware result merge | merged paper hardware table |
| 11. Supplemental Apple Case Study | Observability/portability supplement | Apple supplemental tables/figures |
| 12. Intel Workload-Order Stress Test | Workload-order robustness | Intel stress-test outputs |
| 13. Optional Apple Transition Study | Optional transition robustness | Apple transition outputs |
| 14. Final Reproducibility Checklist | Required-artifact and claim-status audit | explicit completion/incompletion status |

## 5. Main TCAD Tables

Use the Section 5 results gallery as the source for the result section. The five main tables are:

| Paper Table | Notebook Artifact | Why It Matters |
|---|---|---|
| Table I. Selected CITADEL operating points | `gallery_table1_selected_operating_points.csv` | Best configuration per setup/anomaly; use for headline metrics |
| Table II. Workload robustness | `gallery_table2_workload_robustness.csv` | Shows the detector is not tuned to only one workload |
| Table III. Feature-budget and telemetry-cost trade-off | `gallery_table3_feature_budget_tradeoff.csv` | Supports compact feature-set and telemetry-bandwidth claims |
| Table IV. Stable conditional telemetry graph top features | `gallery_table4_stable_graph_top_features.csv` | Shows interpretability and the new CITADEL ranking mechanism |
| Table V. Lifecycle recalibration and deployment feasibility | `gallery_table5_lifecycle_deployment.csv` | Supports SLM drift/recalibration and deployability |

After final Vivado results are available, update Table V or add a dedicated hardware table with:

```text
LUTs, FFs, DSPs, BRAMs, Fmax, timing slack, latency cycles, dynamic power, static power, total power
```

## 6. Main TCAD Figures

Use these figures from the Section 5 results gallery:

| Paper Figure | Notebook Artifact | Recommended Subsection |
|---|---|---|
| Figure 1. Full DSE heatmap | `gallery_fig1_dse_heatmap.png` | Design-space operating-point comparison |
| Figure 2. Full stable graph network | `gallery_fig4_full_stable_graph_network.png` | Stable conditional telemetry structure |
| Figure 3. Stable feature compass | `gallery_fig5_stable_feature_compass.png` | Hardware-aware feature ranking |
| Figure 4. Lifecycle benign-drift trend | `gallery_fig6c_lifecycle_benign_drift_trend.png` | Drift and recalibration evidence |
| Figure 5. RTL/FPGA deployment passport | `rtl_fpga_deployment_passport.png` | Hardware implementation summary |

These figures are saved under:

```text
results/notebook_run/tcad_ablation/paper_figures/
```

## 7. Suggested TCAD Result Section Order

Use this order in Overleaf:

```latex
\subsection{Full Design-Space Sweep}
\subsection{Detection Quality Across Anomaly Classes}
\subsection{Feature-Budget and Telemetry-Cost Trade-Off}
\subsection{Stable Conditional Telemetry Graph Interpretation}
\subsection{Fixed-Point CINTAS Sensitivity}
\subsection{CINTAS Hardware-Cost Analysis}
\subsection{RTL/FPGA Validation}
\subsection{Lifecycle Drift and Recalibration}
\subsection{Supplemental Portability Study}
```

The Apple study belongs in the last subsection or in an appendix/supplement. It is useful evidence, but it should not drive the core hardware claims.

## 8. MacBook To ASU Vivado Flow

Use the same immutable CITADEL commit on the analysis host and the ASU Vivado
host. Do not copy generated tables between mismatched source trees; the RTL
launcher already contains the four frozen Table VI configurations and hashes
the RTL, Tcl, parser, plan, and reports in its run manifest.

On ASU/Linux, set up Vivado 2025.2 from the ASU tools mount. Run the
vendor-provided C-shell setup through `tcsh`, even when your login shell is Bash:

```bash
cd ~/CITADEL
cp /usr/local/tools/vivado/2025.2/Vivado/settings64.csh ~/settings64_vivado_2025_2.csh
tcsh -c 'source ~/settings64_vivado_2025_2.csh; rehash; vivado -version'
```

Materialize the immutable archived reference, inspect the plan, and then run
the strict launcher into a fresh output directory:

```bash
cd ~/CITADEL
git status --short
uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl
uv run --frozen python scripts/reproduce_rtl.py --dry-run
tcsh -c 'source ~/settings64_vivado_2025_2.csh; cd ~/CITADEL; uv run --frozen python scripts/reproduce_rtl.py --output-root results/reproduced/asu-rtl'
```

Never write a reproduction run into the archived
`results/notebook_run/rtl_sweep` directory or replace its source helpers from
`origin/main`. Choose a new output-root name for each attempt. The launcher
requires Vivado 2025.2 build 6299465, part `xc7a200tfbg676-1`, and a 25 ns
period, then produces an explicit `comparison_report.json`. The parser requires
the exact `run_config.csv` schema and literal `25.000` ns value and verifies
that every report and `post_synth.dcp` is present and materialized.

Each generated configuration folder should contain:

```text
utilization.rpt
timing_summary.rpt
power.rpt
post_synth.dcp
run_config.csv
vivado.log
vivado.jou
```

Retain `reproduction_plan.json`, `run_manifest.json`, and
`comparison_report.json`, and record these values for the RTL/FPGA validation
subsection:

```text
FPGA part, Vivado version, LUTs, FFs, DSPs, BRAMs, timing status, and FPGA power estimate
```

If local inspection is needed, transfer only the uniquely named reproduction
bundle back to a different isolated directory on the MacBook:

```bash
mkdir -p ~/CITADEL/results/reproduced/from-asu
rsync -avz 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/reproduced/asu-rtl/' \
  ~/CITADEL/results/reproduced/from-asu/
```

Back on the MacBook, inspect the recorded status and source identity directly:

```bash
cd ~/CITADEL
python -m json.tool results/reproduced/from-asu/comparison_report.json
python -m json.tool results/reproduced/from-asu/run_manifest.json
```

Do not copy these files into `results/notebook_run/rtl_sweep/` or stage them as
replacements for the archive. A separately curated artifact
release is the appropriate publication mechanism for a new reference bundle.

## 9. Result Values To Update In The Paper

Use:

```text
results/reproduced/<run-id>/notebook_run/paper_tbd_replacements.csv
```

This table is generated inside each isolated core/all run; it is not an
archived reference at the audited legacy snapshot. Use only the file belonging
to the run whose receipt and comparison report passed.

to replace:

```latex
\citadelBestAucpr
\citadelBestRocauc
\citadelFeatureReduction
\citadelAreaOverhead
\citadelPowerOverhead
\citadelPrecisionLoss
```

Also update the prose values for:

```text
best MCC
best F1
best balanced accuracy
false-positive rate
best feature budget
best decision-block length
best fixed-point Q format
area overhead
power overhead
Vivado LUT/FF/DSP/BRAM/Fmax/power
drift false-positive reduction after recalibration
```

## 10. Quality Gates Before Submission

Do not freeze paper results until all gates pass:

1. `git status --porcelain` is empty at start and remains unchanged through completion; the manifest/receipt records the same full commit at both boundaries.
2. `TCAD_PRESET = "full"` when reconstructing Table VI; use `"balanced"` only for a shorter development/revalidation DSE.
3. `SEED = 123` and `THREADS = 1`.
4. Git LFS telemetry files are materialized, not pointer files.
5. `run_manifest.json` exists for TCAD ablation, graph/ranking sensitivity, and lifecycle drift.
6. `graph_sensitivity_claims.json` reports `PASS`, with every range endpoint tied to a setup/event and variant row.
7. Section 5 displays the paper-facing tables and figures.
8. Fixed-point error is small enough that the chosen Q format preserves ranking and threshold behavior.
9. RTL lint is clean or all warnings are explained.
10. RTL simulation matches notebook golden vectors.
11. Vivado synthesis and post-synthesis reports provide timing estimates, utilization, and power for the target FPGA.
12. Apple results are labeled supplemental and not mixed into hardware-cost claims.

## 11. How This Advances The Research

CITADEL advances the original edge telemetry idea in a useful TCAD direction because it connects four pieces that are usually reported separately:

1. benign-only telemetry learning,
2. compact feature selection,
3. fixed-point hardware scoring, and
4. lifecycle drift/recalibration.

The strongest novelty is not just better accuracy. The stronger story is that CITADEL turns telemetry analytics into a deployable SLM flow: learn a stable feature set, sweep the hardware-aware choices, quantify the feature/latency/power trade-off, export fixed-point constants, verify RTL, and keep checking whether the field reference has become stale.

For the future, the work is promising if the final paper avoids overclaiming. The strongest version of the paper should include:

- full DSE results across anomaly classes and workloads,
- DROOP improvements reported honestly with FPR,
- stable conditional graph interpretation,
- fixed-point sensitivity,
- lifecycle recalibration,
- real Vivado or ASIC-oriented synthesis numbers,
- a supplemental Apple observability study.

The highest-impact improvement is the RTL/FPGA validation. Once CINTAS is simulated against golden vectors and synthesized in Vivado, the paper becomes much more than an analytics extension; it becomes a reproducible hardware-aware SLM methodology.

## 12. Final Paper Checklist

Before final submission:

```text
[ ] Full paper-point notebook run completed.
[ ] Frozen-point graph/ranking sensitivity claim audit passed.
[ ] Section 5 tables and figures exported.
[ ] Paper TBD replacement CSV checked.
[ ] RTL golden vectors exported.
[ ] RTL lint and simulation completed.
[ ] Vivado synthesis and post-synthesis reporting completed.
[ ] RTL/FPGA numbers merged through Section 10.
[ ] Apple case study kept supplemental.
[ ] Overleaf macros replaced.
[ ] Captions and claims match the generated artifacts.
```
