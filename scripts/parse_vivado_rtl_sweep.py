#!/usr/bin/env python3
"""Build rtl_resource_summary.csv from Vivado report folders.

The script uses only Python's standard library so it can run on the ASU server
without extra packages.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


DEFAULT_CONFIGS = {
    "A_DROOP": {"setup": "A", "scenario": "DROOP", "top_k": 15, "fixed_point_q": 15, "window_size": 1000},
    "A_RH": {"setup": "A", "scenario": "RH", "top_k": 20, "fixed_point_q": 8, "window_size": 550},
    "B_DROOP": {"setup": "B", "scenario": "DROOP", "top_k": 15, "fixed_point_q": 15, "window_size": 200},
    "B_SPECTRE": {"setup": "B", "scenario": "SPECTRE", "top_k": 30, "fixed_point_q": 8, "window_size": 700},
}

EXPECTED_TAGS = tuple(sorted(DEFAULT_CONFIGS))
EXPECTED_PART = "xc7a200tfbg676-1"
EXPECTED_TOOL_PREFIX = "Vivado v.2025.2 (lin64) Build 6299465"
EXPECTED_CLOCK_PERIOD_NS = "25.000"
RUN_CONFIG_FIELDS = (
    "tag",
    "part",
    "features",
    "q",
    "samples_per_block",
    "clock_period_ns",
)
REPORT_FILENAMES = (
    "post_synth.dcp",
    "power.rpt",
    "run_config.csv",
    "timing_summary.rpt",
    "utilization.rpt",
    "vivado.jou",
    "vivado.log",
)
ROOT_REPORT_FILENAMES = ("reproduction_plan.json",)
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
REPOSITORY = Path(__file__).resolve().parents[1]
ARCHIVED_ROOT = (REPOSITORY / "results" / "notebook_run" / "rtl_sweep").resolve()


def read_text(path: Path) -> str:
    return path.read_text(errors="ignore") if path.exists() else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(LFS_POINTER_PREFIX)).startswith(LFS_POINTER_PREFIX)
    except OSError:
        return False


def portable_path(path: Path, repository: Path) -> str:
    """Prefer a repository-relative path without rejecting external work dirs."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(repository.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def repository_commit_for_path(root: Path) -> str | None:
    """Return the commit that last changed the archived report bundle."""
    try:
        relative = root.resolve().relative_to(REPOSITORY).as_posix()
        value = subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", relative],
            cwd=REPOSITORY,
            text=True,
        ).strip()
        return value or None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def table_used(text: str, label: str) -> int | float | None:
    match = re.search(rf"\|\s*{re.escape(label)}\*?\s*\|\s*([0-9.]+)\s*\|", text)
    if not match:
        return None
    value = match.group(1)
    return float(value) if "." in value else int(value)


def util_pct(text: str, label: str) -> float | None:
    match = re.search(
        rf"\|\s*{re.escape(label)}\*?\s*\|\s*[0-9.]+\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*\d+\s*\|\s*([0-9.]+)\s*\|",
        text,
    )
    return float(match.group(1)) if match else None


def first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return float(match.group(1)) if match else None


def run_config(folder: Path) -> dict[str, str]:
    path = folder / "run_config.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def expected_run_config(tag: str, *, expected_part: str) -> dict[str, str]:
    """Return the exact Tcl configuration contract for one archived tag."""
    cfg = DEFAULT_CONFIGS[tag]
    return {
        "tag": tag,
        "part": expected_part,
        "features": str(cfg["top_k"]),
        "q": str(cfg["fixed_point_q"]),
        "samples_per_block": str(cfg["window_size"]),
        "clock_period_ns": EXPECTED_CLOCK_PERIOD_NS,
    }


def validate_folder_contract(folder: Path, *, expected_part: str) -> list[str]:
    """Validate report presence and the exact, non-tolerant run configuration."""
    tag = folder.name
    failures: list[str] = []
    if tag not in DEFAULT_CONFIGS:
        return [f"{tag}: unexpected configuration tag"]

    for filename in REPORT_FILENAMES:
        path = folder / filename
        if not path.is_file():
            failures.append(f"{tag}: missing required report {filename}")
        elif path.stat().st_size == 0:
            failures.append(f"{tag}: required report is empty: {filename}")
        elif is_lfs_pointer(path):
            failures.append(f"{tag}: required report is still a Git LFS pointer: {filename}")

    path = folder / "run_config.csv"
    if not path.is_file():
        return failures
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            observed_fields = tuple(reader.fieldnames or ())
            config_rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        failures.append(f"{tag}: cannot read run_config.csv: {exc}")
        return failures

    if observed_fields != RUN_CONFIG_FIELDS:
        failures.append(
            f"{tag}: run_config.csv fields must be {RUN_CONFIG_FIELDS}, "
            f"observed {observed_fields}"
        )
    if len(config_rows) != 1:
        failures.append(
            f"{tag}: run_config.csv must contain exactly one data row, observed {len(config_rows)}"
        )
        return failures

    expected = expected_run_config(tag, expected_part=expected_part)
    observed = config_rows[0]
    for field in RUN_CONFIG_FIELDS:
        if observed.get(field) != expected[field]:
            failures.append(
                f"{tag}: run_config.{field} expected {expected[field]!r}, "
                f"observed {observed.get(field)!r}"
            )
    return failures


def infer_config(tag: str, folder: Path) -> dict[str, object]:
    cfg = dict(DEFAULT_CONFIGS.get(tag, {}))
    rcfg = run_config(folder)
    if rcfg:
        cfg.setdefault("setup", tag.split("_", 1)[0])
        cfg.setdefault("scenario", tag.split("_", 1)[1] if "_" in tag else tag)
        for output_field, input_field in (
            ("top_k", "features"),
            ("fixed_point_q", "q"),
            ("window_size", "samples_per_block"),
        ):
            fallback = int(cfg.get(output_field, 0) or 0)
            try:
                cfg[output_field] = int(rcfg.get(input_field, fallback))
            except (TypeError, ValueError):
                # The exact validator reports the malformed field. Retaining a
                # safe value here lets the parser still emit a FAIL manifest.
                cfg[output_field] = fallback
    return cfg


def parse_folder(folder: Path) -> dict[str, object]:
    tag = folder.name
    cfg = infer_config(tag, folder)
    util = read_text(folder / "utilization.rpt")
    timing = read_text(folder / "timing_summary.rpt")
    power = read_text(folder / "power.rpt")
    log = read_text(folder / "vivado.log")
    rcfg = run_config(folder)

    device = rcfg.get("part", "unknown")
    match = re.search(r"\| Device\s*:\s*([^\n]+)", util)
    if match:
        device = match.group(1).strip()

    tool_version = "unknown"
    match = re.search(r"\| Tool Version\s*:\s*([^\n]+)", util)
    if match:
        tool_version = match.group(1).strip()

    wns = first_float(r"Worst Slack\s+(-?[0-9.]+)ns", timing)
    clock_period = first_float(r"Requirement:\s*([0-9.]+)ns", timing)
    if clock_period is None:
        clock_period = float(rcfg.get("clock_period_ns", 0.0) or 0.0)
    timing_met = (
        wns >= 0.0
        if wns is not None
        else "Timing constraints are met" in timing and "Timing constraints are not met" not in timing
    )

    fmax_mhz = None
    if clock_period and wns is not None and clock_period - wns > 0:
        fmax_mhz = round(1000.0 / (clock_period - wns), 2)

    total_power_w = first_float(r"\|\s*Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)\s*\|", power)
    dynamic_power_w = first_float(r"\|\s*Dynamic \(W\)\s*\|\s*([0-9.]+)\s*\|", power)
    static_power_w = first_float(r"\|\s*Device Static \(W\)\s*\|\s*([0-9.]+)\s*\|", power)
    confidence = ""
    match = re.search(r"\|\s*Confidence Level\s*\|\s*([^|]+)\|", power)
    if match:
        confidence = match.group(1).strip()

    synth_ok = "synth_design completed successfully" in log
    power_ok = "report_power completed successfully" in log
    top_k = int(cfg.get("top_k", 0) or 0)
    window_size = int(cfg.get("window_size", 0) or 0)

    return {
        "setup": cfg.get("setup", ""),
        "scenario": cfg.get("scenario", tag),
        "top_k": top_k,
        "fixed_point_q": cfg.get("fixed_point_q", ""),
        "window_size": window_size,
        "tag": tag,
        "target_part": device,
        "tool_version": tool_version,
        "luts": table_used(util, "Slice LUTs"),
        "luts_pct": util_pct(util, "Slice LUTs"),
        "ffs": table_used(util, "Slice Registers"),
        "ffs_pct": util_pct(util, "Slice Registers"),
        "dsps": table_used(util, "DSPs"),
        "dsp_pct": util_pct(util, "DSPs"),
        "brams": table_used(util, "Block RAM Tile"),
        "bram_pct": util_pct(util, "Block RAM Tile"),
        "iobs": table_used(util, "Bonded IOB"),
        "iob_pct": util_pct(util, "Bonded IOB"),
        "clock_period_ns": clock_period,
        "wns_ns": wns,
        "timing_met": timing_met,
        "fmax_mhz_est": fmax_mhz,
        "total_power_mw": round(total_power_w * 1000, 3) if total_power_w is not None else "",
        "dynamic_power_mw": round(dynamic_power_w * 1000, 3) if dynamic_power_w is not None else "",
        "static_power_mw": round(static_power_w * 1000, 3) if static_power_w is not None else "",
        "power_confidence": confidence,
        "synth_ok": synth_ok,
        "power_ok": power_ok,
        "latency_cycles": top_k * window_size if top_k and window_size else "",
        "status": "synthesized" if synth_ok else "check_log",
    }


def validate_rows(
    rows: list[dict[str, object]],
    *,
    expected_part: str,
    expected_tool_prefix: str,
) -> list[str]:
    failures: list[str] = []
    observed_tags = tuple(sorted(str(row["tag"]) for row in rows))
    if observed_tags != EXPECTED_TAGS:
        failures.append(f"expected tags {EXPECTED_TAGS}, observed {observed_tags}")
    for row in rows:
        tag = str(row["tag"])
        if row["target_part"] != expected_part:
            failures.append(f"{tag}: expected part {expected_part}, observed {row['target_part']}")
        if not str(row["tool_version"]).startswith(expected_tool_prefix):
            failures.append(
                f"{tag}: expected tool prefix {expected_tool_prefix!r}, observed {row['tool_version']!r}"
            )
        for field in ("synth_ok", "power_ok", "timing_met"):
            if row[field] is not True:
                failures.append(f"{tag}: {field} is {row[field]!r}")
    return failures


def build_manifest(
    root: Path,
    output: Path,
    rows: list[dict[str, object]],
    failures: list[str],
    *,
    expected_part: str,
    expected_tool_prefix: str,
) -> dict[str, object]:
    repository = REPOSITORY
    root = root.resolve()
    output = output.resolve()
    inputs: list[dict[str, object]] = []
    for filename in ROOT_REPORT_FILENAMES:
        path = root / filename
        if path.is_file():
            inputs.append(
                {
                    "path": portable_path(path, repository),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        for filename in REPORT_FILENAMES:
            path = folder / filename
            if path.is_file():
                inputs.append(
                    {
                        "path": portable_path(path, repository),
                        "sha256": sha256_file(path),
                        "size_bytes": path.stat().st_size,
                    }
                )
    source_paths = [
        repository / ".python-version",
        repository / "pyproject.toml",
        repository / "uv.lock",
        repository / "scripts" / "vivado_cintas_synth.tcl",
        repository / "scripts" / "parse_vivado_rtl_sweep.py",
        repository / "scripts" / "reproduce_rtl.py",
        *sorted((repository / "rtl" / "cintas").glob("*.sv")),
    ]
    sources = [
        {
            "path": portable_path(path, repository),
            "sha256": sha256_file(path),
        }
        for path in source_paths
    ]
    plan_path = root / "reproduction_plan.json"
    plan: dict[str, object] = {}
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 2,
        "status": "PASS" if not failures else "FAIL",
        "comparison_scope": "parsed synthesis metrics; report and checkpoint bytes are archival evidence",
        "report_bundle_commit": repository_commit_for_path(root),
        "required_tool_prefix": expected_tool_prefix,
        "required_target_part": expected_part,
        "required_tags": list(EXPECTED_TAGS),
        "failures": failures,
        "parsed_rows": rows,
        "source_files": sources,
        "report_files": inputs,
        "summary": {
            "path": portable_path(output, repository),
            "sha256": sha256_file(output),
            "size_bytes": output.stat().st_size,
        },
    }
    plan_provenance = plan.get("source_provenance")
    if isinstance(plan_provenance, dict):
        source_commit = plan_provenance.get("repository_commit")
        manifest["source_commit"] = source_commit
        manifest["report_bundle_commit"] = source_commit
        manifest["report_bundle_commit_basis"] = "pre-Vivado source checkout HEAD"
        manifest["source_provenance"] = plan_provenance
    if "runtime" in plan:
        manifest["runtime"] = plan["runtime"]
    return manifest


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_output_targets(root: Path, output: Path, manifest: Path) -> tuple[Path, Path, Path]:
    """Require explicit, unused outputs outside the immutable reference tree."""
    root = root.expanduser().resolve()
    output = output.expanduser().resolve()
    manifest = manifest.expanduser().resolve()
    if output == manifest:
        raise ValueError("--output and --manifest must be different files")
    if _inside(output, ARCHIVED_ROOT) or _inside(manifest, ARCHIVED_ROOT):
        raise ValueError(
            "Parser outputs cannot be written under the immutable archived RTL root; "
            "use a fresh results/reproduced/<run-id>/rtl_sweep directory."
        )
    existing = [str(path) for path in (output, manifest) if path.exists()]
    if existing:
        raise FileExistsError(
            f"Parser output targets already exist; choose a fresh run directory: {existing}"
        )
    return root, output, manifest


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse one complete Vivado RTL report bundle into fresh diagnostic outputs."
    )
    parser.add_argument("--root", type=Path, required=True, help="Vivado report-bundle root to read")
    parser.add_argument("--output", type=Path, required=True, help="Fresh summary CSV outside the archive")
    parser.add_argument("--manifest", type=Path, required=True, help="Fresh manifest JSON outside the archive")
    parser.add_argument("--expected-part", default=EXPECTED_PART)
    parser.add_argument("--expected-tool-prefix", default=EXPECTED_TOOL_PREFIX)
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Parse noncanonical reports without enforcing the archived tool/part contract.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    report_root, output, manifest_path = validate_output_targets(
        args.root, args.output, args.manifest
    )

    folders = [
        item
        for item in sorted(report_root.iterdir())
        if item.is_dir() and (item / "utilization.rpt").exists()
    ]
    rows = [parse_folder(folder) for folder in folders]
    if not rows:
        raise SystemExit(f"No Vivado report folders found under {report_root}")

    failures = validate_rows(
        rows,
        expected_part=args.expected_part,
        expected_tool_prefix=args.expected_tool_prefix,
    )
    for folder in folders:
        failures.extend(
            validate_folder_contract(folder, expected_part=args.expected_part)
        )
    if failures and not args.no_verify:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {output}")
    for row in rows:
        print(
            f"{row['tag']}: LUT={row['luts']} FF={row['ffs']} DSP={row['dsps']} "
            f"BRAM={row['brams']} WNS={row['wns_ns']}ns Power={row['total_power_mw']}mW "
            f"TimingMet={row['timing_met']}"
        )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        report_root,
        output,
        rows,
        failures,
        expected_part=args.expected_part,
        expected_tool_prefix=args.expected_tool_prefix,
    )
    with manifest_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {manifest_path} ({manifest['status']})")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        # --no-verify is explicitly diagnostic; its fresh manifest remains FAIL.


if __name__ == "__main__":
    main()
