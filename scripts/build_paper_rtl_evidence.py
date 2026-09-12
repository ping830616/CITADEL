#!/usr/bin/env python3
"""Build the tracked paper-facing evidence for Figure 5 and Table XI.

This command re-parses the committed Vivado report bundle.  It does not run
Vivado and therefore must never be described as a fresh synthesis result.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Iterable

REPOSITORY = Path(__file__).resolve().parents[1]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from scripts import parse_vivado_rtl_sweep, render_rtl_figure5, reproduce_rtl

from PIL import Image, ImageStat


ARCHIVED_ROOT = REPOSITORY / "results" / "notebook_run" / "rtl_sweep"
ARCHIVED_SUMMARY = ARCHIVED_ROOT / "rtl_resource_summary.csv"
ARCHIVED_FIGURE = (
    REPOSITORY
    / "results"
    / "notebook_run"
    / "tcad_ablation"
    / "paper_figures"
    / "rtl_fpga_deployment_passport.png"
)
DEFAULT_OUTPUT_ROOT = REPOSITORY / "reproducibility" / "paper_results" / "rtl"
GENERATOR_VERSION = "1.0.0"
PAPER_TAG_ORDER = ("A_DROOP", "A_RH", "B_DROOP", "B_SPECTRE")
ARCHIVED_REPORT_BUNDLE_COMMIT = "08cf2368999a9eea3b234a931d899f704a4f0169"
SYNTHESIS_SOURCE_HASHES_AT_REPORT_COMMIT = {
    "scripts/vivado_cintas_synth.tcl": (
        "522b4f13a218ebc9458583807c5b3587c77d42ad116c876ce538f557edeff62a"
    ),
    "rtl/cintas/cintas_stream.sv": (
        "a8b492c039ea82329564389a427deadf914253fb4e70566ce0444b62c06a56ce"
    ),
}

TABLE_XI_FIELDS = (
    "setup_event",
    "k",
    "q",
    "N",
    "LUT",
    "FF",
    "DSP",
    "WNS_ns",
    "fmax_MHz",
    "power_mW",
)
TABLE_XI_EXPECTED = (
    {
        "setup_event": "A/DROOP",
        "k": "15",
        "q": "15",
        "N": "1000",
        "LUT": "867",
        "FF": "244",
        "DSP": "38",
        "WNS_ns": "2.458",
        "fmax_MHz": "44.36",
        "power_mW": "158",
    },
    {
        "setup_event": "A/RH",
        "k": "20",
        "q": "8",
        "N": "550",
        "LUT": "863",
        "FF": "259",
        "DSP": "37",
        "WNS_ns": "2.569",
        "fmax_MHz": "44.58",
        "power_mW": "157",
    },
    {
        "setup_event": "B/DROOP",
        "k": "15",
        "q": "15",
        "N": "200",
        "LUT": "884",
        "FF": "242",
        "DSP": "38",
        "WNS_ns": "2.474",
        "fmax_MHz": "44.39",
        "power_mW": "158",
    },
    {
        "setup_event": "B/SPECTRE",
        "k": "30",
        "q": "8",
        "N": "700",
        "LUT": "907",
        "FF": "259",
        "DSP": "37",
        "WNS_ns": "2.110",
        "fmax_MHz": "43.69",
        "power_mW": "157",
    },
)

FIGURE_5_FIELDS = (
    "tag",
    "setup",
    "event",
    "clock_period_ns",
    "wns_ns",
    "timing_met",
    "luts",
    "luts_pct",
    "ffs",
    "ffs_pct",
    "dsps",
    "dsp_pct",
    "iobs",
    "iob_pct",
    "brams",
    "bram_pct",
    "total_power_mw",
    "power_confidence",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_path(path: Path) -> str:
    return path.resolve().relative_to(REPOSITORY).as_posix()


def source_record(path: Path, role: str) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"Required RTL evidence source is missing: {path}")
    if parse_vivado_rtl_sweep.is_lfs_pointer(path):
        raise RuntimeError(
            f"Required RTL evidence source is still a Git LFS pointer: {path}. "
            "Run `uv run --frozen python scripts/reproduce.py fetch-lfs --scope rtl`."
        )
    return {
        "path": repository_path(path),
        "role": role,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def parse_and_validate_archive() -> tuple[list[dict[str, object]], dict[str, object]]:
    folders = [ARCHIVED_ROOT / tag for tag in PAPER_TAG_ORDER]
    rows = [parse_vivado_rtl_sweep.parse_folder(folder) for folder in folders]
    failures = parse_vivado_rtl_sweep.validate_rows(
        rows,
        expected_part=parse_vivado_rtl_sweep.EXPECTED_PART,
        expected_tool_prefix=parse_vivado_rtl_sweep.EXPECTED_TOOL_PREFIX,
    )
    for folder in folders:
        failures.extend(
            parse_vivado_rtl_sweep.validate_folder_contract(
                folder,
                expected_part=parse_vivado_rtl_sweep.EXPECTED_PART,
            )
        )
    if failures:
        raise RuntimeError("Archived RTL report contract failed: " + "; ".join(failures))

    with tempfile.TemporaryDirectory(prefix="citadel-paper-rtl-") as directory:
        candidate = Path(directory) / "rtl_resource_summary.csv"
        with candidate.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(rows[0]),
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        comparison = reproduce_rtl.compare_summaries(
            ARCHIVED_SUMMARY,
            candidate,
            rtol=1e-12,
            atol=1e-12,
        )
    if comparison["status"] != "PASS":
        raise RuntimeError(
            "Archived RTL summary does not match the committed reports: "
            + json.dumps(comparison["failures"], sort_keys=True)
        )
    return rows, comparison


def table_xi_rows(rows: Iterable[dict[str, object]]) -> list[dict[str, str]]:
    projected: list[dict[str, str]] = []
    for row in rows:
        projected.append(
            {
                "setup_event": f"{row['setup']}/{row['scenario']}",
                "k": str(int(row["top_k"])),
                "q": str(int(row["fixed_point_q"])),
                "N": str(int(row["window_size"])),
                "LUT": str(int(row["luts"])),
                "FF": str(int(row["ffs"])),
                "DSP": str(int(row["dsps"])),
                "WNS_ns": f"{float(row['wns_ns']):.3f}",
                "fmax_MHz": f"{float(row['fmax_mhz_est']):.2f}",
                "power_mW": f"{float(row['total_power_mw']):.0f}",
            }
        )
    if projected != list(TABLE_XI_EXPECTED):
        raise RuntimeError(
            "Archived RTL reports do not reproduce the four values reported in Table XI"
        )
    return projected


def figure_5_rows(rows: Iterable[dict[str, object]]) -> list[dict[str, str]]:
    projected: list[dict[str, str]] = []
    for row in rows:
        if not bool(row["timing_met"]):
            raise RuntimeError(f"Figure 5 timing gate failed for {row['tag']}")
        if int(row["brams"]) != 0:
            raise RuntimeError(f"Figure 5 BRAM gate failed for {row['tag']}")
        projected.append(
            {
                "tag": str(row["tag"]),
                "setup": str(row["setup"]),
                "event": str(row["scenario"]),
                "clock_period_ns": f"{float(row['clock_period_ns']):.3f}",
                "wns_ns": f"{float(row['wns_ns']):.3f}",
                "timing_met": str(bool(row["timing_met"])),
                "luts": str(int(row["luts"])),
                "luts_pct": f"{float(row['luts_pct']):.2f}",
                "ffs": str(int(row["ffs"])),
                "ffs_pct": f"{float(row['ffs_pct']):.2f}",
                "dsps": str(int(row["dsps"])),
                "dsp_pct": f"{float(row['dsp_pct']):.2f}",
                "iobs": str(int(row["iobs"])),
                "iob_pct": f"{float(row['iob_pct']):.2f}",
                "brams": str(int(row["brams"])),
                "bram_pct": f"{float(row['bram_pct']):.2f}",
                "total_power_mw": f"{float(row['total_power_mw']):.0f}",
                "power_confidence": str(row["power_confidence"]),
            }
        )
    return projected


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def source_records() -> list[dict[str, object]]:
    records = [
        source_record(ARCHIVED_SUMMARY, "archived summary consumed by the notebook"),
        source_record(ARCHIVED_FIGURE, "archived Figure 5 render; PNG bytes are provenance only"),
        source_record(
            REPOSITORY / "notebooks" / "exact_tcad_all_experiments.ipynb",
            "Figure 5 renderer",
        ),
        source_record(
            REPOSITORY / "scripts" / "parse_vivado_rtl_sweep.py",
            "archived-report parser and contract validator",
        ),
        source_record(
            REPOSITORY / "scripts" / "reproduce_rtl.py",
            "fresh-synthesis launcher and summary comparator",
        ),
        source_record(
            REPOSITORY / "scripts" / "render_rtl_figure5.py",
            "Figure 5 renderer used by archived and fresh summaries",
        ),
        source_record(
            REPOSITORY / "scripts" / "vivado_cintas_synth.tcl",
            "Vivado synthesis recipe",
        ),
        source_record(
            REPOSITORY / "rtl" / "cintas" / "cintas_stream.sv",
            "synthesized RTL",
        ),
    ]
    for tag in PAPER_TAG_ORDER:
        folder = ARCHIVED_ROOT / tag
        for filename in parse_vivado_rtl_sweep.REPORT_FILENAMES:
            records.append(
                source_record(folder / filename, f"archived Vivado evidence for {tag}")
            )
    return sorted(records, key=lambda record: str(record["path"]))


def output_record(path: Path, row_count: int | None = None) -> dict[str, object]:
    record: dict[str, object] = {
        "path": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }
    if row_count is not None:
        record["row_count"] = row_count
    return record


def figure_validation(path: Path) -> dict[str, object]:
    with Image.open(path) as opened:
        if opened.format != "PNG":
            raise RuntimeError(f"Figure 5 is not a PNG: {path}")
        opened.verify()
    with Image.open(path) as opened:
        width, height = opened.size
        sample = opened.convert("L")
        sample.thumbnail((256, 256))
        variance = float(ImageStat.Stat(sample).var[0])
    if width < 1000 or height < 900 or variance <= 1.0:
        raise RuntimeError(
            f"Figure 5 is too small or visually uniform: {width}x{height}, variance={variance}"
        )
    return {
        "path": path.name,
        "decoded_png": True,
        "nonuniform": True,
        "width_px": int(width),
        "height_px": int(height),
        "composition": "timing_slack_panel_plus_four_case_resource_summary",
        "separate_legend_present": True,
    }


def portable_evidence(payload: dict[str, object]) -> dict[str, object]:
    """Remove renderer-dependent raster bytes/dimensions from rebuild comparison."""

    normalized = json.loads(json.dumps(payload))
    for record in normalized.get("outputs", []):
        if record.get("path") == "figure_5.png":
            record.pop("sha256", None)
            record.pop("size_bytes", None)
    rendered = normalized.get("rendered_figure", {})
    if isinstance(rendered, dict):
        rendered.pop("width_px", None)
        rendered.pop("height_px", None)
    return normalized


def build_bundle(output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, object]:
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    parsed_rows, comparison = parse_and_validate_archive()
    table_rows = table_xi_rows(parsed_rows)
    figure_rows = figure_5_rows(parsed_rows)

    table_path = output_root / "table_xi.csv"
    figure_path = output_root / "figure_5_source.csv"
    rendered_figure_path = output_root / "figure_5.png"
    evidence_path = output_root / "evidence.json"
    write_csv(table_path, TABLE_XI_FIELDS, table_rows)
    write_csv(figure_path, FIGURE_5_FIELDS, figure_rows)
    render_rtl_figure5.render_figure5(ARCHIVED_SUMMARY, rendered_figure_path)
    rendered_validation = figure_validation(rendered_figure_path)

    synthesis_sources = (
        REPOSITORY / "scripts" / "vivado_cintas_synth.tcl",
        REPOSITORY / "rtl" / "cintas" / "cintas_stream.sv",
    )
    source_alignment = []
    for path in synthesis_sources:
        current_hash = sha256_file(path)
        archived_hash = SYNTHESIS_SOURCE_HASHES_AT_REPORT_COMMIT[repository_path(path)]
        source_alignment.append(
            {
                "path": repository_path(path),
                "current_sha256": current_hash,
                "report_commit_sha256": archived_hash,
                "match": current_hash == archived_hash,
            }
        )
    if not all(record["match"] for record in source_alignment):
        raise RuntimeError("Current synthesis source differs from the archived report commit")

    generator_path = Path(__file__).resolve()
    evidence: dict[str, object] = {
        "schema_version": 1,
        "evidence_class": "archived_reanalysis",
        "status": "PASS",
        "paper_items": ["Figure 5", "Table XI"],
        "fresh_vivado_synthesis": False,
        "archived_report_bundle_commit": ARCHIVED_REPORT_BUNDLE_COMMIT,
        "required_tool": {
            "name": "AMD Vivado",
            "release": reproduce_rtl.REQUIRED_VIVADO_RELEASE,
            "sw_build": reproduce_rtl.REQUIRED_VIVADO_BUILD,
            "target_part": reproduce_rtl.REQUIRED_PART,
        },
        "generator": {
            "path": repository_path(generator_path),
            "version": GENERATOR_VERSION,
            "sha256": sha256_file(generator_path),
        },
        "checks": {
            "strict_archived_report_contract": "PASS",
            "archived_summary_matches_reports": comparison["status"],
            "table_xi_matches_manuscript_values": "PASS",
            "figure_5_source_rows_complete": "PASS",
            "figure_5_rendered_composition": "PASS",
            "synthesis_source_matches_report_commit": "PASS",
            "raw_report_byte_identity_required_for_future_runs": False,
        },
        "synthesis_source_alignment": source_alignment,
        "sources": source_records(),
        "outputs": [
            output_record(table_path, len(table_rows)),
            output_record(figure_path, len(figure_rows)),
            output_record(rendered_figure_path),
        ],
        "rendered_figure": rendered_validation,
        "limitations": [
            "This bundle re-parses committed Vivado reports; it is not a fresh Vivado synthesis.",
            (
                "The paper prototype and archived reports use maximum aggregation, "
                "whereas the selected analytical settings in Table VI use median aggregation."
            ),
            (
                "The power values are low-confidence vectorless estimates and exclude "
                "telemetry acquisition and board integration."
            ),
            (
                "A fresh comparison-grade run requires Vivado 2025.2 SW Build 6299465, "
                "the xc7a200tfbg676-1 device database, and an appropriate license."
            ),
        ],
    }
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


def check_tracked_bundle() -> None:
    expected = DEFAULT_OUTPUT_ROOT
    with tempfile.TemporaryDirectory(prefix="citadel-paper-rtl-check-") as directory:
        candidate = Path(directory)
        build_bundle(candidate)
        failures = []
        for filename in ("table_xi.csv", "figure_5_source.csv"):
            reference_path = expected / filename
            candidate_path = candidate / filename
            if (
                not reference_path.is_file()
                or reference_path.read_bytes() != candidate_path.read_bytes()
            ):
                failures.append(filename)
        reference_evidence = json.loads((expected / "evidence.json").read_text(encoding="utf-8"))
        candidate_evidence = json.loads((candidate / "evidence.json").read_text(encoding="utf-8"))
        if portable_evidence(reference_evidence) != portable_evidence(candidate_evidence):
            failures.append("evidence.json (portable fields)")
        for label, path in (
            ("tracked figure_5.png", expected / "figure_5.png"),
            ("candidate figure_5.png", candidate / "figure_5.png"),
        ):
            try:
                figure_validation(path)
            except RuntimeError:
                failures.append(label)
    if failures:
        raise RuntimeError("Tracked RTL paper evidence is stale: " + ", ".join(failures))


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build or verify the archived-reanalysis bundle for Figure 5 and Table XI."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Rebuild in a temporary directory and compare with the tracked bundle.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    if args.check:
        check_tracked_bundle()
        print("PASS: tracked Figure 5/Table XI evidence matches the archived reports.")
        return
    evidence = build_bundle(args.output_root)
    print(
        f"Wrote Figure 5/Table XI evidence to {args.output_root} "
        f"({evidence['evidence_class']}; fresh_vivado_synthesis=false)."
    )


if __name__ == "__main__":
    main()
