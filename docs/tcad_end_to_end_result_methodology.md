# TCAD End-To-End Result Methodology

This document is the start-to-finish runbook for turning the CITADEL repository into the result section of the TCAD paper. It explains what to run, where each result comes from, which figures and tables should appear in the manuscript, and how to combine MacBook notebook results with ASU/Linux Vivado hardware results.

The short version is:

`MacBook notebook -> CITADEL balanced sweep -> paper tables/figures -> golden vectors -> ASU Vivado RTL/FPGA -> hardware CSV -> MacBook merge -> final TCAD figures/tables`.

## 1. Goal

The TCAD paper should show that CITADEL is more than an offline anomaly detector. The result section should support five claims:

1. CITADEL detects SLM-relevant anomalies with strong block-level metrics.
2. CITADEL keeps the runtime feature set compact through stable conditional telemetry ranking.
3. The design-space sweep explains how feature budget, decision-block length, aggregation, weighting, and fixed-point precision affect accuracy and cost.
4. Fixed-point CINTAS is numerically stable enough for edge hardware.
5. The deployed detector can be checked and recalibrated when benign telemetry drifts.

The Apple observability study is useful, but it should remain supplemental. It supports portability and observability discussion; it should not be mixed into the main CINTAS area, power, or FPGA claims.

## 2. Main Artifacts

Run everything from the single notebook:

```text
notebooks/exact_tcad_all_experiments.ipynb
```

Important output folders:

```text
results/notebook_run/tcad_ablation/
results/notebook_run/tcad_ablation/paper_figures/
results/notebook_run/lifecycle_drift/
results/notebook_run/fpga/
results/notebook_run/rtl_sweep/
results/notebook_run/paper_tbd_replacements.csv
```

Important source files:

```text
configs/tcad_grid_balanced.json
configs/tcad_grid_full.json
rtl/cintas/cintas_stream.sv
hardware/cintas_operator_costs.csv
environment.yml
```

## 3. Machine Roles

Use the machines this way.

| Machine | Role | Why |
|---|---|---|
| MacBook M2 | Main notebook run, result inspection, figures, paper writing, final merge | Fast enough for notebook work and convenient for Overleaf/result review |
| ASU Linux server | Long notebook run if needed, Vivado synthesis/place-and-route | Better for remote long jobs and vendor FPGA tools |
| MacBook M2 with OSS CAD Suite | RTL lint, open-source synthesis checks, optional simulation workflow | Good for reproducible local hardware sanity checks |

Recommended final workflow:

1. Run notebook Sections 1--16 on MacBook or ASU.
2. Generate fixed-point golden vectors from Section 16.
3. Run Vivado synthesis/place-and-route on ASU/Linux.
4. Save Vivado results in `results/notebook_run/rtl_sweep/rtl_resource_summary.csv`.
5. Pull or copy results back to MacBook.
6. Run notebook Sections 17 and 11 to merge and display final paper results.

## 4. Full Notebook Procedure

From a fresh clone or updated clone:

```bash
cd ~/CITADEL
git pull --ff-only origin main
git lfs pull
conda env update -f environment.yml --prune
conda activate citadel-slm
python -m jupyter lab notebooks/exact_tcad_all_experiments.ipynb
```

Use these notebook settings for final paper results:

```python
SEED = 123
THREADS = 1
DATA_MODE = "real"
TCAD_PRESET = "balanced"
RUN_REPEAT_CHECK = True
```

Use `"full"` only for an optional exhaustive ASU/Linux sensitivity run.

Run the notebook from top to bottom. The key paper sections are:

| Notebook Section | Purpose | Main Output |
|---|---|---|
| 4. Full Design-Space Sweep | Main CITADEL sweep | `tcad_ablation_summary.csv`, fold results, selected features |
| 5. Detection Quality Across Anomaly Classes | Main accuracy summary | anomaly-class metrics |
| 6. Feature-Budget and Telemetry-Cost Trade-Off | Compact telemetry evidence | feature-budget tables and plots |
| 7. Causal Telemetry Graph Interpretation | Stable conditional graph evidence | feature ranks, graph files |
| 8. Fixed-Point CINTAS Sensitivity | Numerical hardware evidence | fixed-point error by Q format |
| 9. CINTAS Hardware-Cost Analysis | Analytical hardware-cost evidence | operator, area, power estimates |
| 10. Lifecycle Drift and Recalibration | SLM lifecycle evidence | drift/recalibration CSVs |
| 11. TCAD Results Gallery | Paper-facing tables and figures | selected operating points, cost tables, graph figures, RTL figure, lifecycle figure |
| 16. Export Fixed-Point Golden Vectors For RTL | RTL verification input | golden-vector CSV |
| 17. Merge Future RTL/FPGA Results Into The TCAD Table | Hardware result merge | merged paper hardware table |
| 18. Supplemental Apple Case Study | Observability/portability supplement | Apple supplemental tables/figures |

## 5. Main TCAD Tables

Use Section 11 as the source for the result section. The five main tables are:

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

Use these five figures from Section 11:

| Paper Figure | Notebook Artifact | Recommended Subsection |
|---|---|---|
| Figure 1. Full DSE heatmap | `gallery_fig1_full_dse_heatmap.png` | Full Design-Space Sweep |
| Figure 2. Detection quality bars | `gallery_fig2_detection_quality.png` | Detection Quality Across Anomaly Classes |
| Figure 3. Workload robustness heatmap | `gallery_fig3_workload_heatmap.png` | Detection Quality or Workload Robustness |
| Figure 4. Stable feature map | `gallery_fig4_stable_feature_map.png` | Causal Telemetry Graph Interpretation |
| Figure 5. Deployment feasibility | `gallery_fig5_deployment_feasibility.png` | Fixed-Point, Hardware Cost, and Lifecycle |

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

First run the notebook through the RTL/FPGA handoff cells. Then copy the generated handoff files to ASU. The `results/` folder is ignored by Git, so direct file transfer is clearer than committing generated artifacts:

```bash
cd ~/CITADEL
scp results/notebook_run/fpga/cintas_setupA_q15_golden_vectors.csv \
  'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/fpga/'
scp results/notebook_run/tcad_ablation/tcad_ablation_summary.csv \
  'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/tcad_ablation/'
scp results/notebook_run/tcad_ablation/tcad_selected_features.csv \
  'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/tcad_ablation/'
scp results/notebook_run/tcad_ablation/paper_figures/section4_vivado_best_settings_queue.csv \
  'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/tcad_ablation/paper_figures/'
```

On ASU/Linux, set up Vivado 2025.2 from the ASU tools mount:

```bash
cd ~/CITADEL
cp /usr/local/tools/vivado/2025.2/Vivado/settings64.csh ~/settings64_vivado_2025_2.csh
source ~/settings64_vivado_2025_2.csh
rehash
vivado -version
```

If Bash cannot source the `.csh` setup file, use `tcsh -c`. The ASU `tcsh` does not support `-lc`:

```bash
tcsh -c 'source ~/settings64_vivado_2025_2.csh; vivado -version'
```

Fetch only the Vivado helper if `git pull` is blocked by local notebook edits or missing Git LFS:

```bash
git fetch origin main
mkdir -p scripts
git show origin/main:scripts/vivado_cintas_synth.tcl > scripts/vivado_cintas_synth.tcl
git show origin/main:scripts/parse_vivado_rtl_sweep.py > scripts/parse_vivado_rtl_sweep.py
ls -lh scripts/vivado_cintas_synth.tcl
```

Create the output folders and run the four selected CITADEL operating points. The commands use a larger Artix-7 package and a 25 ns clock so the validation wrapper avoids the small-package I/O limit and is checked at a realistic post-synthesis timing target:

```bash
mkdir -p results/notebook_run/rtl_sweep/A_DROOP
mkdir -p results/notebook_run/rtl_sweep/A_RH
mkdir -p results/notebook_run/rtl_sweep/B_DROOP
mkdir -p results/notebook_run/rtl_sweep/B_SPECTRE

vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/A_DROOP/vivado.log -journal results/notebook_run/rtl_sweep/A_DROOP/vivado.jou -tclargs A_DROOP xc7a200tfbg676-1 15 15 1000 25.000
vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/A_RH/vivado.log -journal results/notebook_run/rtl_sweep/A_RH/vivado.jou -tclargs A_RH xc7a200tfbg676-1 20 8 550 25.000
vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/B_DROOP/vivado.log -journal results/notebook_run/rtl_sweep/B_DROOP/vivado.jou -tclargs B_DROOP xc7a200tfbg676-1 15 15 200 25.000
vivado -mode batch -source scripts/vivado_cintas_synth.tcl -log results/notebook_run/rtl_sweep/B_SPECTRE/vivado.log -journal results/notebook_run/rtl_sweep/B_SPECTRE/vivado.jou -tclargs B_SPECTRE xc7a200tfbg676-1 30 8 700 25.000
python3 scripts/parse_vivado_rtl_sweep.py --root results/notebook_run/rtl_sweep
```

Each folder should contain:

```text
utilization.rpt
timing_summary.rpt
power.rpt
post_synth.dcp
run_config.csv
vivado.log
vivado.jou
```

Record these values for the RTL/FPGA validation subsection:

```text
FPGA part, Vivado version, LUTs, FFs, DSPs, BRAMs, timing status, and FPGA power estimate
```

Transfer the RTL sweep folder back to the MacBook:

```bash
rsync -avz 'asurite\hsiaopin@149.169.30.50:~/CITADEL/results/notebook_run/rtl_sweep/' \
  ~/CITADEL/results/notebook_run/rtl_sweep/
```

Back on MacBook:

```bash
cd ~/CITADEL
```

Then rerun:

```text
Section 17. Merge Future RTL/FPGA Results Into The TCAD Table
Section 11. TCAD Results Gallery
```

If you intentionally want to version the final hardware CSV despite `results/` being ignored, use `git add -f`:

```bash
git add -f results/notebook_run/rtl_sweep/rtl_resource_summary.csv
git commit -m "Add Vivado FPGA synthesis results"
git push origin main
```

## 9. Result Values To Update In The Paper

Use:

```text
results/notebook_run/paper_tbd_replacements.csv
```

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

1. `git status` is clean or the run manifest clearly records the final commit.
2. `TCAD_PRESET = "balanced"` for the normal paper run, or `"full"` for the optional exhaustive sensitivity run.
3. `SEED = 123` and `THREADS = 1`.
4. Git LFS telemetry files are materialized, not pointer files.
5. `run_manifest.json` exists for TCAD ablation and lifecycle drift.
6. Section 11 displays all five tables and five figures.
7. Fixed-point error is small enough that the chosen Q format preserves ranking and threshold behavior.
8. RTL lint is clean or all warnings are explained.
9. RTL simulation matches notebook golden vectors.
10. Vivado synthesis/place-and-route reports timing, utilization, and power for the target FPGA.
11. Apple results are labeled supplemental and not mixed into hardware-cost claims.

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
[ ] Balanced notebook run completed.
[ ] Section 11 tables and figures exported.
[ ] Paper TBD replacement CSV checked.
[ ] RTL golden vectors exported.
[ ] RTL lint and simulation completed.
[ ] Vivado synthesis/place-and-route completed.
[ ] RTL/FPGA numbers merged through Section 17.
[ ] Apple case study kept supplemental.
[ ] Overleaf macros replaced.
[ ] Captions and claims match the generated artifacts.
```
