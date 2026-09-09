# Continuous Intel Workload Transition Campaign

This campaign is the submission quality follow up to the preserved data workload order stress test. It starts a new Intel PCM process for every run and keeps that process active while PAMPAR workload processes change at recorded boundaries. This produces independently identified runs and directly observed workload transitions.

## Requirements

Run the campaign on the Intel Linux machine represented by Setup A or Setup B. Configure the pinned PAMPAR and Intel PCM revisions described in `docs/telemetry_collection.md`. Intel PCM normally requires elevated access.

The default workload set contains 12 PAMPAR applications. SH is excluded because its original input image is not preserved. Include SH only when the exact input and dimensions are supplied with `--sh-input`, `--sh-height`, and `--sh-width`.

## Inspect The Plan First

For Setup A:

```text
python3 scripts/run_intel_transition_campaign.py \
  --setup A \
  --pampar-root /absolute/path/to/PAMPAR \
  --pcm-bin /absolute/path/to/pcm/build/bin/pcm \
  --dry-run
```

Change `--setup A` to `--setup B` for the DDR5 testbed. The dry run does not execute PAMPAR or Intel PCM.

## Full Collection

Remove `--dry-run` after checking the paths and phase plans. The defaults collect five runs, two calibration cycles, three evaluation cycles, 20 seconds per workload phase, a requested 0.1 second PCM interval, and a two minute cooldown between runs. For 12 workloads, one setup takes approximately 108 minutes.

Each run has:

- a new Intel PCM process;
- a separately seeded workload order in every cycle;
- one uninterrupted PCM file spanning every workload switch;
- explicit phase start and end timestamps;
- workload invocation identifiers and exit status; and
- host, command, version, and protocol information in the manifest.

The workload process is repeated if it finishes before the phase ends. At a boundary, the old process group is terminated and the next workload starts immediately. A run fails if this gap exceeds three seconds, Intel PCM exits early, a workload fails, or any planned phase is absent.

The campaign does not change voltage, firmware, cooling, or frequency policy. It directly evaluates rapid benign workload changes, which is sufficient for a reviewer request framed as workload **or** operating condition changes. Do not describe it as a controlled operating condition experiment.

## Analysis

After the campaign is complete, run:

```text
python3 scripts/analyze_intel_transition_campaign.py \
  --campaign-dir data/telemetry/raw/intel_transition_campaigns/<campaign_id>
```

The parser uses the Date and Time fields emitted by Intel PCM to align samples with the recorded phase timestamps. It rejects a file when those timestamps cannot be parsed. Cumulative counter state is not reconstructed: Intel PCM interval counts, ratios, energy, and residency values are retained, while temperature and voltage fields are converted to continuous first differences before calibration.

For each run, the first two cycles calibrate the feature set, normalization, score, and threshold. The threshold uses the finite sample corrected upper calibration rank for a 1 percent target and a strict score exceedance. These quantities remain frozen during the last three cycles. Results include overall benign false positive rate, the first block after each measured switch, later blocks within a phase, stabilization, the two block persistence comparison, and a one sided exact binomial reference compatibility check against the 1 percent target. The primary evidence is the individual run distribution and its mean and sample standard deviation; the binomial check is secondary because consecutive decision blocks may not be statistically independent. The campaign summary also reports the range and a descriptive 95 percent bootstrap interval.

## Outputs

Raw collection files are stored without overwriting prior runs:

```text
data/telemetry/raw/intel_transition_campaigns/<campaign_id>/
  campaign_manifest.json
  runs/<run_id>/collection_manifest.json
  runs/<run_id>/pcm_raw.csv
  runs/<run_id>/phase_events.csv
  runs/<run_id>/workload_invocations.csv
```

Analysis outputs are written under:

```text
results/notebook_run/intel_transition_campaigns/<campaign_id>/
```

Do not claim independent continuous Intel results until the campaign and every run manifest report `complete`, the CPU identity matches the intended setup, the PCM timestamp audit passes, and the individual run values have been inspected.
