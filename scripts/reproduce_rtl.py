#!/usr/bin/env python3
"""Reproduce the four archived CITADEL Vivado synthesis configurations.

This launcher deliberately writes to an isolated result directory.  It checks
the installed Vivado release before running any synthesis, invokes the
repository's canonical Tcl script sequentially, parses the resulting reports,
and compares the parsed metrics with the archived summary.  Raw Vivado report,
log, journal, and checkpoint bytes contain host/session metadata and are not
expected to be byte-identical across machines.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REPOSITORY = Path(__file__).resolve().parents[1]
TCL_SCRIPT = REPOSITORY / "scripts" / "vivado_cintas_synth.tcl"
PARSER_SCRIPT = REPOSITORY / "scripts" / "parse_vivado_rtl_sweep.py"
ARCHIVED_ROOT = REPOSITORY / "results" / "notebook_run" / "rtl_sweep"
ARCHIVED_SUMMARY = ARCHIVED_ROOT / "rtl_resource_summary.csv"

REQUIRED_VIVADO_RELEASE = "2025.2"
REQUIRED_VIVADO_BUILD = "6299465"
REQUIRED_REPORT_TOOL_PREFIX = "Vivado v.2025.2 (lin64) Build 6299465"
REQUIRED_PART = "xc7a200tfbg676-1"
DEFAULT_OUTPUT_ROOT = REPOSITORY / "results" / "reproduced" / "rtl_sweep_vivado_2025_2"
REPRODUCED_ROOT = REPOSITORY / "results" / "reproduced"
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


@dataclass(frozen=True)
class RtlConfiguration:
    tag: str
    features: int
    q: int
    samples_per_block: int
    clock_period_ns: str = "25.000"


# Keep this order aligned with the archived command sequence and the paper.
CONFIGURATIONS = (
    RtlConfiguration("A_DROOP", features=15, q=15, samples_per_block=1000),
    RtlConfiguration("A_RH", features=20, q=8, samples_per_block=550),
    RtlConfiguration("B_DROOP", features=15, q=15, samples_per_block=200),
    RtlConfiguration("B_SPECTRE", features=30, q=8, samples_per_block=700),
)

EXACT_INTEGER_FIELDS = {
    "top_k",
    "fixed_point_q",
    "window_size",
    "luts",
    "ffs",
    "dsps",
    "brams",
    "iobs",
    "latency_cycles",
}
TOLERANT_FLOAT_FIELDS = {
    "luts_pct",
    "ffs_pct",
    "dsp_pct",
    "bram_pct",
    "iob_pct",
    "wns_ns",
    "fmax_mhz_est",
    "total_power_mw",
    "dynamic_power_mw",
    "static_power_mw",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_paths() -> tuple[Path, ...]:
    """Return every repository source file that controls the RTL result."""
    return (
        REPOSITORY / ".python-version",
        REPOSITORY / "pyproject.toml",
        REPOSITORY / "uv.lock",
        Path(__file__).resolve(),
        PARSER_SCRIPT,
        TCL_SCRIPT,
        *sorted((REPOSITORY / "rtl" / "cintas").glob("*.sv")),
    )


def capture_source_provenance(*, allow_dirty: bool) -> dict[str, object]:
    """Capture the immutable Git/source state before invoking Vivado."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=REPOSITORY,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Unable to capture the repository Git state") from exc

    dirty_entries = [line for line in status.splitlines() if line]
    if dirty_entries and not allow_dirty:
        preview = ", ".join(dirty_entries[:5])
        if len(dirty_entries) > 5:
            preview += f", ... ({len(dirty_entries)} entries total)"
        raise RuntimeError(
            "Repository is not clean; comparison-grade RTL runs require an immutable "
            f"checkout. Dirty entries: {preview}. Use --allow-dirty only for a "
            "deliberately non-archival development run."
        )

    files: list[dict[str, object]] = []
    for path in source_paths():
        if not path.is_file():
            raise FileNotFoundError(f"Required RTL source is missing: {path}")
        files.append(
            {
                "path": path.relative_to(REPOSITORY).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "repository_commit": commit,
        "repository_clean": not dirty_entries,
        "dirty_override_used": bool(dirty_entries and allow_dirty),
        "git_status_porcelain": dirty_entries,
        "source_files": files,
    }


def runtime_provenance(vivado: str, version_output: str) -> dict[str, object]:
    resolved_vivado = shutil.which(vivado) or vivado
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "vivado_executable": resolved_vivado,
        "vivado_version_output": version_output.splitlines(),
        "vivado_version_output_sha256": hashlib.sha256(
            version_output.encode("utf-8")
        ).hexdigest(),
        "deterministic_environment": {"LANG": "C", "LC_ALL": "C", "TZ": "UTC"},
    }


def require_final_snapshot_unchanged(
    provenance: dict[str, object],
    *,
    reference: Path,
    reference_sha256: str,
    raise_on_failure: bool = True,
) -> dict[str, object]:
    """Revalidate every source/reference identity after parsing and comparison."""
    try:
        commit_at_finish = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip()
        status_at_finish_text = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=REPOSITORY,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Unable to revalidate the repository Git state") from exc

    status_at_finish = [line for line in status_at_finish_text.splitlines() if line]
    source_changes: list[str] = []
    for record in provenance["source_files"]:
        path = REPOSITORY / str(record["path"])
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            source_changes.append(str(record["path"]))

    reference = reference.resolve()
    reference_unchanged = bool(
        reference.is_file() and sha256_file(reference) == reference_sha256
    )
    commit_unchanged = commit_at_finish == provenance["repository_commit"]
    status_unchanged = status_at_finish == provenance["git_status_porcelain"]
    snapshot_unchanged = bool(
        commit_unchanged
        and status_unchanged
        and not source_changes
        and reference_unchanged
    )
    failures = [
        name
        for name, passed in (
            ("HEAD", commit_unchanged),
            ("Git worktree status", status_unchanged),
            ("controlling source files", not source_changes),
            ("archived reference", reference_unchanged),
        )
        if not passed
    ]
    result: dict[str, object] = {
        "status": "PASS" if snapshot_unchanged else "FAIL",
        "failures": failures,
        "repository_commit_at_finish": commit_at_finish,
        "git_status_porcelain_at_finish": status_at_finish,
        "commit_unchanged": commit_unchanged,
        "git_status_unchanged": status_unchanged,
        "source_files_unchanged": not source_changes,
        "changed_source_files": source_changes,
        "archived_reference": str(reference),
        "archived_reference_sha256": reference_sha256,
        "archived_reference_unchanged": reference_unchanged,
    }
    if failures and raise_on_failure:
        raise RuntimeError(
            "RTL source/reference snapshot changed during execution; result is invalid "
            f"({', '.join(failures)})"
        )
    return result


def require_exact_vivado_version(version_output: str) -> None:
    """Raise when ``vivado -version`` is not the archived release/build."""
    release = re.search(r"(?m)^Vivado v([0-9]+\.[0-9]+) \(64-bit\)\s*$", version_output)
    build = re.search(r"(?m)^SW Build ([0-9]+)(?:\s+.*)?$", version_output)
    observed_release = release.group(1) if release else "not found"
    observed_build = build.group(1) if build else "not found"
    if observed_release != REQUIRED_VIVADO_RELEASE or observed_build != REQUIRED_VIVADO_BUILD:
        raise RuntimeError(
            "Vivado version mismatch: required "
            f"v{REQUIRED_VIVADO_RELEASE} SW Build {REQUIRED_VIVADO_BUILD}; "
            f"observed release {observed_release}, build {observed_build}."
        )


def vivado_command(
    vivado: str,
    configuration: RtlConfiguration,
    *,
    workdir: Path,
) -> list[str]:
    generated = workdir / "results" / "notebook_run" / "rtl_sweep" / configuration.tag
    return [
        vivado,
        "-mode",
        "batch",
        "-source",
        str(TCL_SCRIPT),
        "-log",
        str(generated / "vivado.log"),
        "-journal",
        str(generated / "vivado.jou"),
        "-tclargs",
        configuration.tag,
        REQUIRED_PART,
        str(configuration.features),
        str(configuration.q),
        str(configuration.samples_per_block),
        configuration.clock_period_ns,
    ]


def parser_command(output_root: Path) -> list[str]:
    return [
        sys.executable,
        str(PARSER_SCRIPT),
        "--root",
        str(output_root),
        "--output",
        str(output_root / "rtl_resource_summary.csv"),
        "--manifest",
        str(output_root / "run_manifest.json"),
        "--expected-part",
        REQUIRED_PART,
        "--expected-tool-prefix",
        REQUIRED_REPORT_TOOL_PREFIX,
    ]


def build_plan(vivado: str, output_root: Path, reference: Path) -> dict[str, object]:
    placeholder = Path("$CITADEL_VIVADO_WORKDIR")
    return {
        "schema_version": 2,
        "execution": "sequential",
        "required_vivado": {
            "release": REQUIRED_VIVADO_RELEASE,
            "sw_build": REQUIRED_VIVADO_BUILD,
        },
        "required_part": REQUIRED_PART,
        "required_clock_period_ns": "25.000",
        "clean_checkout_required": True,
        "canonical_tcl": TCL_SCRIPT.relative_to(REPOSITORY).as_posix(),
        "output_root": str(output_root),
        "archived_reference": str(reference),
        "version_command": shlex.join([vivado, "-version"]),
        "configurations": [
            {
                **asdict(configuration),
                "command": shlex.join(
                    vivado_command(vivado, configuration, workdir=placeholder)
                ),
            }
            for configuration in CONFIGURATIONS
        ],
        "parse_command": shlex.join(parser_command(output_root)),
        "comparison_scope": (
            "parsed metrics: configuration identity, clock period, and resource counts exact; "
            "only measured resource percentages, timing, Fmax, and power values are "
            "tolerance-aware; raw report/checkpoint bytes excluded"
        ),
    }


def validate_output_root(output_root: Path) -> Path:
    resolved = output_root.expanduser().resolve()
    try:
        relative = resolved.relative_to(REPRODUCED_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Output root must be inside the isolated {REPRODUCED_ROOT.resolve()} tree: {resolved}"
        ) from exc
    if relative == Path("."):
        raise ValueError("Output root must be a uniquely named run below results/reproduced")
    if resolved.exists():
        raise FileExistsError(
            f"Output root already exists: {resolved}. Choose a fresh directory to preserve evidence."
        )
    return resolved


def finalize_run_manifest(
    output_root: Path,
    *,
    source_provenance: dict[str, object],
    runtime: dict[str, object],
    final_integrity_gate: dict[str, object],
    comparison_path: Path,
    comparison_status: str,
) -> Path:
    """Attach launcher provenance and root-artifact hashes to the parser manifest."""
    manifest_path = output_root / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    plan_path = output_root / "reproduction_plan.json"
    report_paths = {
        Path(str(item["path"])).name
        for item in manifest.get("report_files", [])
        if isinstance(item, dict) and "path" in item
    }
    if "reproduction_plan.json" not in report_paths:
        raise RuntimeError("run_manifest.json does not hash reproduction_plan.json")

    manifest.update(
        {
            "schema_version": max(int(manifest.get("schema_version", 1)), 3),
            "source_commit": source_provenance["repository_commit"],
            "archival_eligible": bool(
                source_provenance["repository_clean"]
                and final_integrity_gate.get("status") == "PASS"
                and comparison_status == "PASS"
            ),
            "source_provenance": source_provenance,
            "final_integrity_gate": final_integrity_gate,
            "runtime": runtime,
            "comparison": {
                "path": comparison_path.relative_to(REPOSITORY).as_posix(),
                "sha256": sha256_file(comparison_path),
                "size_bytes": comparison_path.stat().st_size,
                "status": comparison_status,
            },
        }
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(LFS_POINTER_PREFIX)).startswith(LFS_POINTER_PREFIX)
    except OSError:
        return False


def read_summary(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "tag" not in reader.fieldnames:
            raise ValueError(f"Summary has no tag column: {path}")
        rows: dict[str, dict[str, str]] = {}
        for row in reader:
            tag = row["tag"]
            if tag in rows:
                raise ValueError(f"Duplicate tag {tag!r} in {path}")
            rows[tag] = row
    return list(reader.fieldnames), rows


def _integer_equal(reference: str, candidate: str) -> bool:
    try:
        return int(reference) == int(candidate)
    except ValueError:
        return reference == candidate


def _float_equal(reference: str, candidate: str, *, rtol: float, atol: float) -> bool:
    if reference == "" or candidate == "":
        return reference == candidate
    try:
        return math.isclose(float(reference), float(candidate), rel_tol=rtol, abs_tol=atol)
    except ValueError:
        return reference == candidate


def compare_summaries(
    reference_path: Path,
    candidate_path: Path,
    *,
    rtol: float,
    atol: float,
) -> dict[str, object]:
    """Compare parsed metrics without requiring byte-identical Vivado reports."""
    reference_fields, reference_rows = read_summary(reference_path)
    candidate_fields, candidate_rows = read_summary(candidate_path)
    failures: list[dict[str, object]] = []

    if reference_fields != candidate_fields:
        failures.append(
            {
                "kind": "columns",
                "expected": reference_fields,
                "observed": candidate_fields,
            }
        )

    required_tags = [configuration.tag for configuration in CONFIGURATIONS]
    if sorted(reference_rows) != sorted(required_tags):
        failures.append(
            {
                "kind": "reference_tags",
                "expected": sorted(required_tags),
                "observed": sorted(reference_rows),
            }
        )
    if sorted(candidate_rows) != sorted(required_tags):
        failures.append(
            {
                "kind": "candidate_tags",
                "expected": sorted(required_tags),
                "observed": sorted(candidate_rows),
            }
        )

    for tag in sorted(set(reference_rows) & set(candidate_rows)):
        reference = reference_rows[tag]
        candidate = candidate_rows[tag]
        for field in reference_fields:
            expected = reference.get(field, "")
            observed = candidate.get(field, "")
            if field in EXACT_INTEGER_FIELDS:
                equal = _integer_equal(expected, observed)
                comparison = "exact integer"
            elif field in TOLERANT_FLOAT_FIELDS:
                equal = _float_equal(expected, observed, rtol=rtol, atol=atol)
                comparison = "numeric tolerance"
            else:
                equal = expected == observed
                comparison = "exact text"
            if not equal:
                failures.append(
                    {
                        "kind": "value",
                        "tag": tag,
                        "field": field,
                        "comparison": comparison,
                        "expected": expected,
                        "observed": observed,
                    }
                )

    return {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "reference": str(reference_path),
        "candidate": str(candidate_path),
        "required_tags": required_tags,
        "exact_integer_fields": sorted(EXACT_INTEGER_FIELDS),
        "tolerant_float_fields": sorted(TOLERANT_FLOAT_FIELDS),
        "rtol": rtol,
        "atol": atol,
        "raw_report_byte_identity_required": False,
        "failures": failures,
    }


def run_checked(command: Iterable[str], *, cwd: Path, env: dict[str, str]) -> None:
    printable = shlex.join(list(command))
    print(f"+ {printable}", flush=True)
    subprocess.run(list(command), cwd=cwd, env=env, check=True)


def execute(args: argparse.Namespace) -> int:
    output_root = validate_output_root(args.output_root)
    reference = args.reference.expanduser().resolve()
    plan = build_plan(args.vivado, output_root, reference)
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        print("DRY RUN: no directories were created and no commands were executed.")
        return 0

    if not TCL_SCRIPT.is_file() or not PARSER_SCRIPT.is_file():
        raise FileNotFoundError("Canonical Vivado Tcl or parser script is missing")
    if not reference.is_file() or is_lfs_pointer(reference):
        raise FileNotFoundError(
            f"Archived summary is unavailable: {reference}. Materialize the RTL LFS scope first."
        )

    source_provenance = capture_source_provenance(
        allow_dirty=bool(getattr(args, "allow_dirty", False))
    )

    version_process = subprocess.run(
        [args.vivado, "-version"],
        cwd=REPOSITORY,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    require_exact_vivado_version(version_process.stdout)
    print(
        f"Verified Vivado v{REQUIRED_VIVADO_RELEASE} SW Build {REQUIRED_VIVADO_BUILD}.",
        flush=True,
    )
    runtime = runtime_provenance(args.vivado, version_process.stdout)
    plan["source_provenance"] = source_provenance
    plan["runtime"] = runtime
    plan["dirty_checkout_override"] = bool(source_provenance["dirty_override_used"])
    plan["archived_reference_sha256"] = sha256_file(reference)

    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "reproduction_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    environment = os.environ.copy()
    environment.update({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
    with tempfile.TemporaryDirectory(prefix="citadel-vivado-") as temporary:
        workdir = Path(temporary).resolve()
        shutil.copytree(REPOSITORY / "rtl" / "cintas", workdir / "rtl" / "cintas")
        generated_root = workdir / "results" / "notebook_run" / "rtl_sweep"

        for configuration in CONFIGURATIONS:
            command = vivado_command(args.vivado, configuration, workdir=workdir)
            process_error: subprocess.CalledProcessError | None = None
            try:
                run_checked(command, cwd=workdir, env=environment)
            except subprocess.CalledProcessError as exc:
                process_error = exc

            generated = generated_root / configuration.tag
            destination = output_root / configuration.tag
            if generated.is_dir():
                shutil.move(str(generated), str(destination))
            if process_error is not None:
                raise RuntimeError(
                    f"Vivado failed for {configuration.tag}; retained available logs under {destination}"
                ) from process_error
            if not (destination / "utilization.rpt").is_file():
                raise RuntimeError(
                    f"Vivado completed without the required utilization report for {configuration.tag}"
                )

    run_checked(parser_command(output_root), cwd=REPOSITORY, env=environment)
    comparison = compare_summaries(
        reference,
        output_root / "rtl_resource_summary.csv",
        rtol=args.rtol,
        atol=args.atol,
    )
    comparison_path = output_root / "comparison_report.json"
    comparison_path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {comparison_path} ({comparison['status']})")
    final_integrity_gate = require_final_snapshot_unchanged(
        source_provenance,
        reference=reference,
        reference_sha256=str(plan["archived_reference_sha256"]),
        raise_on_failure=False,
    )
    manifest_path = finalize_run_manifest(
        output_root,
        source_provenance=source_provenance,
        runtime=runtime,
        final_integrity_gate=final_integrity_gate,
        comparison_path=comparison_path,
        comparison_status=str(comparison["status"]),
    )
    print(f"Finalized {manifest_path} with source/runtime provenance.")
    if final_integrity_gate["status"] != "PASS":
        raise RuntimeError(
            "RTL source/reference snapshot changed during execution; result is invalid "
            f"({', '.join(final_integrity_gate['failures'])})"
        )
    if comparison["status"] != "PASS":
        return 1
    print("RTL synthesis metrics reproduce the archived result contract.")
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the four archived CITADEL RTL configurations with the exact Vivado build "
            "and compare parsed metrics."
        )
    )
    parser.add_argument("--vivado", default="vivado", help="Vivado executable or absolute path")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Fresh repository-local output directory; the archive is never overwritten",
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=ARCHIVED_SUMMARY,
        help="Archived parsed summary used as the comparison reference",
    )
    parser.add_argument("--rtol", type=float, default=1e-3, help="Relative tolerance for floats")
    parser.add_argument("--atol", type=float, default=1e-3, help="Absolute tolerance for floats")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the exact plan without checking Vivado, creating directories, or running commands",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "Permit a deliberately non-archival development run from a dirty checkout; "
            "the dirty state is recorded in the manifest"
        ),
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    if args.rtol < 0 or args.atol < 0:
        raise SystemExit("--rtol and --atol must be nonnegative")
    try:
        status = execute(args)
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    raise SystemExit(status)


if __name__ == "__main__":
    main()
