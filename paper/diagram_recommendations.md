# Diagram Recommendations for the TCAD Paper

These figures would help the abstract, introduction, and background tell a clear story before the method section.

## Figure 1: EXACT-TCAD Lifecycle Flow

Purpose: show the full research story in one figure.

Suggested panels:

1. Benign telemetry calibration from compute, memory, and sensor signals.
2. Causal graph learning and COM/MEM/SEN feature ranking.
3. Top-k feature selection and fixed-point CINTAS scoring.
4. Decision-block thresholding and anomaly context.
5. Lifecycle drift monitoring and benign recalibration.
6. RTL/FPGA validation path.

This should replace a generic block diagram. It should show how the TCAD paper extends the ETS version.

## Figure 2: Conference-to-Journal Extension Map

Purpose: make the contribution beyond ETS visually obvious.

Rows:

- ETS EXACT baseline
- TCAD ablation
- heterogeneous validation
- lifecycle drift and recalibration
- RTL/FPGA validation

Columns:

- research question
- experiment
- output table or figure
- reproducibility artifact

This figure can also support the cover letter.

## Figure 3: CINTAS Hardware Datapath

Purpose: connect equations to hardware.

Blocks:

- input telemetry feature
- subtract benign mean
- multiply by reciprocal standard deviation
- absolute-value path for E1
- square path for E2
- weighted accumulation
- lambda mixer
- block aggregator
- threshold comparator
- alert and top-contributor context

Use a simple left-to-right datapath. Avoid decorative styling.

## Figure 4: Design-Space Ablation Matrix

Purpose: show what the TCAD paper studies that the ETS paper did not.

Axes:

- feature budget k
- decision-block length N
- lambda_res
- aggregation operator
- weighting mode
- fixed-point Q format

Outputs:

- MCC, balanced accuracy, AUROC, AUPRC
- Brier score and calibration error
- latency
- feature bandwidth
- area, power, delay, cycles
- fixed-point error

This can be a compact matrix or Sankey-like flow from parameters to metrics.

## Figure 5: Lifecycle Drift and Recalibration Loop

Purpose: explain long-term SLM operation.

Loop:

1. initial benign calibration
2. frozen edge detector
3. in-field benign drift
4. false-positive monitoring
5. safe benign-window selection
6. threshold-only or full recalibration
7. feature-rank stability check

This figure will help reviewers see that lifecycle drift is not an afterthought.
