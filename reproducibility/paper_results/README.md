# Paper-result evidence index

This directory contains only the compact evidence needed to trace the
experimental results printed in Section V. Run the repository-wide audit with:

```bash
uv run --frozen python scripts/reproduce.py verify-paper --scope all
```

`coverage_status: PASS` means every expected paper item and compact file is
present. `traceability_status: PASS` means declared hashes, source records,
rendered-figure checks, and manuscript-value checks pass. These do not imply
that every experiment was freshly rerun; that stricter conclusion is reported
separately as `fresh_clean_rerun_status`.

| Directory | Paper items | Evidence tier |
|---|---|---|
| [`core/`](core/) | Tables VI–X; Figures 3, 4, and 6; Sections V-B, V-F, and V-H | Traceable historical projection (`REFERENCE_ONLY`); use the full core command for a clean candidate run. |
| [`sensitivity/`](sensitivity/) | Section V-D graph/ranking ranges and named reductions | Clean archived run with a passing claim audit. |
| [`rtl/`](rtl/) | Figure 5 and Table XI | Reanalysis of archived Vivado reports; not a fresh synthesis run. |
| [`intel/`](intel/) | Figure 7 and Section V-I | Two clean unchanged runs with complete repeat comparison. |
| [`apple/`](apple/) | Figure 8 and Section V-J | Traceable historical projection (`REFERENCE_ONLY`); use the Apple command for a clean candidate run. |

CSV and JSON files are the portable scientific comparison targets. Rendered
figures are decoded and checked for required composition, but their bytes are
not required to match across font stacks or operating systems.
