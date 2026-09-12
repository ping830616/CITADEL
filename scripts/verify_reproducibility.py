#!/usr/bin/env python3
"""Verify archived CITADEL files and compare independently generated results.

The archive check validates Git/Git-LFS content against a repository-owned
SHA-256 inventory.  The result comparison checks scientific tables with exact
categorical values and tolerant numeric values; it deliberately does not
require byte-identical notebooks, manifests, or raster figures across hosts.
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import hashlib
import json
import math
import subprocess
import sys
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable


POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(POINTER_PREFIX)).startswith(POINTER_PREFIX)
    except OSError:
        return False


def parse_lfs_pointer(path: Path) -> tuple[str | None, int | None]:
    oid: str | None = None
    size: int | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("oid sha256:"):
            oid = line.split(":", 1)[1].strip()
        elif line.startswith("size "):
            size = int(line.split()[1])
    return oid, size


def write_report(payload: dict[str, Any], report_path: Path | None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {report_path}")
    print(rendered, end="")


def selected_for_scope(entry: dict[str, Any], scope: str) -> bool:
    scopes = set(entry.get("scopes", []))
    return (
        scope == "all"
        or scope in scopes
        or "all" in scopes
        or (scope != "source" and "source" in scopes)
    )


def tracked_inventory_paths(root: Path) -> set[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    paths = {item.decode("utf-8") for item in output.split(b"\0") if item}
    paths.discard("reproducibility/archive_manifest.json")
    return paths


def verify_archive(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    inventory_path = (args.inventory or root / "reproducibility" / "archive_manifest.json").resolve()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []

    listed_paths = [str(entry["path"]) for entry in inventory["files"]]
    listed_set = set(listed_paths)
    tracked_set = tracked_inventory_paths(root)
    duplicate_paths = sorted(path for path in listed_set if listed_paths.count(path) > 1)
    for path in duplicate_paths:
        rows.append({"path": path, "storage": None, "status": "DUPLICATE_INVENTORY_ENTRY"})
    for path in sorted(tracked_set - listed_set):
        rows.append({"path": path, "storage": None, "status": "INVENTORY_MISSING_TRACKED_FILE"})
    for path in sorted(listed_set - tracked_set):
        rows.append({"path": path, "storage": None, "status": "INVENTORY_UNTRACKED_ENTRY"})
    if inventory.get("file_count") != len(inventory["files"]):
        rows.append(
            {
                "path": None,
                "storage": None,
                "status": "INVENTORY_FILE_COUNT_MISMATCH",
                "declared": inventory.get("file_count"),
                "observed": len(inventory["files"]),
            }
        )

    for entry in inventory["files"]:
        if not selected_for_scope(entry, args.scope):
            continue
        path = root / entry["path"]
        row: dict[str, Any] = {
            "path": entry["path"],
            "storage": entry["storage"],
            "status": "PASS",
        }
        if not path.is_file():
            row["status"] = "MISSING"
        elif entry["storage"] == "git-lfs" and is_lfs_pointer(path):
            oid, size = parse_lfs_pointer(path)
            row["materialized"] = False
            if oid != entry["sha256"] or size != entry["size_bytes"]:
                row["status"] = "POINTER_METADATA_MISMATCH"
            elif args.require_materialized:
                row["status"] = "LFS_OBJECT_NOT_MATERIALIZED"
            else:
                row["status"] = "PASS_POINTER_METADATA"
        else:
            row["materialized"] = True
            observed_size = path.stat().st_size
            observed_sha = sha256_file(path)
            row["observed_size_bytes"] = observed_size
            row["observed_sha256"] = observed_sha
            if observed_size != entry["size_bytes"]:
                row["status"] = "SIZE_MISMATCH"
            elif observed_sha != entry["sha256"]:
                row["status"] = "HASH_MISMATCH"
        rows.append(row)

    if not rows:
        rows.append(
            {
                "path": None,
                "storage": None,
                "status": "NO_INVENTORY_ENTRIES_FOR_SCOPE",
            }
        )
    failures = [row for row in rows if not row["status"].startswith("PASS")]
    overall_status = "FAIL" if failures else "PASS"
    payload = {
        "schema_version": 1,
        "check": "archive_integrity",
        "scope": args.scope,
        "require_materialized": bool(args.require_materialized),
        "checked_files": len(rows),
        "failures": len(failures),
        "status": overall_status,
        "details": rows if args.verbose or failures else [],
    }
    write_report(payload, args.report)
    return 0 if not failures else 1


def parse_number(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def equal_cell(left: str, right: str, *, rtol: float, atol: float) -> bool:
    if left == right:
        return True
    left_num = parse_number(left)
    right_num = parse_number(right)
    if left_num is None or right_num is None:
        return False
    if math.isnan(left_num) and math.isnan(right_num):
        return True
    return math.isclose(left_num, right_num, rel_tol=rtol, abs_tol=atol)


def compare_csv(
    reference: Path,
    candidate: Path,
    *,
    rtol: float,
    atol: float,
    key_columns: Iterable[str] = (),
    ignored_columns: Iterable[str] = (),
    unordered_delimited_columns: dict[str, str] | None = None,
    max_examples: int = 8,
) -> dict[str, Any]:
    """Compare CSVs positionally or by declared scientific identity keys.

    A keyed comparison rejects duplicate, missing, and extra identities while
    allowing serialization order to vary. Only explicitly declared delimited
    set-valued columns are order-insensitive; all other categorical values and
    non-tied ordinal ranks remain exact.
    """
    examples: list[dict[str, Any]] = []
    mismatch_count = 0
    key_names = tuple(key_columns)
    ignored = set(ignored_columns)
    unordered = dict(unordered_delimited_columns or {})
    columns: list[str] = []

    def compare_pair(
        identity: tuple[str, ...],
        left_row: dict[str, str],
        right_row: dict[str, str],
    ) -> None:
        nonlocal mismatch_count
        for column in columns:
            if column in ignored or column in key_names:
                continue
            left = left_row[column]
            right = right_row[column]
            delimiter = unordered.get(column)
            if delimiter is not None:
                left_items = sorted(item.strip() for item in left.split(delimiter) if item.strip())
                right_items = sorted(item.strip() for item in right.split(delimiter) if item.strip())
                equal = left_items == right_items
            else:
                equal = equal_cell(left, right, rtol=rtol, atol=atol)
            if equal:
                continue
            mismatch_count += 1
            if len(examples) < max_examples:
                example: dict[str, Any] = {
                    "column": column,
                    "reference": left,
                    "candidate": right,
                }
                if key_names:
                    example["key"] = dict(zip(key_names, identity, strict=True))
                else:
                    example["row"] = int(identity[0])
                if delimiter is not None:
                    example["comparison"] = f"unordered set split by {delimiter!r}"
                examples.append(example)

    def comparison_payload(rows: int) -> dict[str, Any]:
        return {
            "status": "PASS" if mismatch_count == 0 else "VALUE_MISMATCH",
            "rows": rows,
            "mismatches": mismatch_count,
            "examples": examples,
            "key_columns": list(key_names),
            "ignored_columns": sorted(ignored & set(columns)),
            "unordered_delimited_columns": {
                column: delimiter for column, delimiter in unordered.items() if column in columns
            },
        }

    with reference.open(newline="", encoding="utf-8-sig") as left_handle, candidate.open(
        newline="", encoding="utf-8-sig"
    ) as right_handle:
        left_reader = csv.DictReader(left_handle)
        right_reader = csv.DictReader(right_handle)
        left_header = left_reader.fieldnames
        right_header = right_reader.fieldnames
        if left_header != right_header:
            return {
                "status": "HEADER_MISMATCH",
                "reference_header": left_header,
                "candidate_header": right_header,
            }
        columns = left_header or []
        missing_contract_columns = sorted(set(key_names) - set(columns))
        if missing_contract_columns:
            return {
                "status": "CONTRACT_COLUMN_MISSING",
                "missing_columns": missing_contract_columns,
            }
        if not key_names:
            marker = object()
            left_count = 0
            right_count = 0
            for index, (left_row, right_row) in enumerate(
                zip_longest(left_reader, right_reader, fillvalue=marker),
                start=1,
            ):
                if left_row is not marker:
                    left_count += 1
                if right_row is not marker:
                    right_count += 1
                if left_row is marker or right_row is marker:
                    continue
                compare_pair((str(index),), left_row, right_row)
            if left_count != right_count:
                return {
                    "status": "ROW_COUNT_MISMATCH",
                    "reference_rows": left_count,
                    "candidate_rows": right_count,
                }
            return comparison_payload(left_count)
        left_rows = list(left_reader)
        right_rows = list(right_reader)

    def index_rows(rows: list[dict[str, str]], side: str):
        indexed: dict[tuple[str, ...], dict[str, str]] = {}
        duplicates: list[tuple[str, ...]] = []
        for row in rows:
            key = tuple(row[name] for name in key_names)
            if key in indexed:
                duplicates.append(key)
            else:
                indexed[key] = row
        if duplicates:
            return None, {
                "status": "DUPLICATE_KEY",
                "side": side,
                "key_columns": list(key_names),
                "duplicate_keys": [list(key) for key in duplicates[:max_examples]],
            }
        return indexed, None

    left_index, error = index_rows(left_rows, "reference")
    if error:
        return error
    right_index, error = index_rows(right_rows, "candidate")
    if error:
        return error
    assert left_index is not None and right_index is not None
    left_keys = set(left_index)
    right_keys = set(right_index)
    if left_keys != right_keys:
        return {
            "status": "KEY_MISMATCH",
            "key_columns": list(key_names),
            "missing_candidate_keys": [list(key) for key in sorted(left_keys - right_keys)[:max_examples]],
            "extra_candidate_keys": [list(key) for key in sorted(right_keys - left_keys)[:max_examples]],
        }
    pairs = [
        (key, left_index[key], right_index[key])
        for key in sorted(left_keys)
    ]

    for identity, left_row, right_row in pairs:
        compare_pair(identity, left_row, right_row)
    return comparison_payload(len(pairs))


def strip_json_keys(value: Any, ignored: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_json_keys(child, ignored)
            for key, child in value.items()
            if key not in ignored
        }
    if isinstance(value, list):
        return [strip_json_keys(child, ignored) for child in value]
    return value


def _compare_json_values(
    left: Any,
    right: Any,
    *,
    path: str,
    rtol: float,
    atol: float,
    examples: list[dict[str, Any]],
    max_examples: int,
) -> int:
    """Compare JSON structurally, allowing tolerance only for JSON numbers."""
    if isinstance(left, bool) or isinstance(right, bool):
        equal = type(left) is type(right) and left == right
        if not equal and len(examples) < max_examples:
            examples.append({"path": path, "reference": left, "candidate": right})
        return 0 if equal else 1
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        left_number = float(left)
        right_number = float(right)
        equal = (
            math.isnan(left_number) and math.isnan(right_number)
        ) or math.isclose(left_number, right_number, rel_tol=rtol, abs_tol=atol)
        if not equal and len(examples) < max_examples:
            examples.append({"path": path, "reference": left, "candidate": right})
        return 0 if equal else 1
    if isinstance(left, dict) and isinstance(right, dict):
        mismatches = 0
        left_keys = set(left)
        right_keys = set(right)
        for key in sorted(left_keys | right_keys):
            child_path = f"{path}.{key}"
            if key not in left or key not in right:
                mismatches += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "path": child_path,
                            "reason": "missing_key",
                            "reference_present": key in left,
                            "candidate_present": key in right,
                        }
                    )
                continue
            mismatches += _compare_json_values(
                left[key],
                right[key],
                path=child_path,
                rtol=rtol,
                atol=atol,
                examples=examples,
                max_examples=max_examples,
            )
        return mismatches
    if isinstance(left, list) and isinstance(right, list):
        mismatches = 0
        if len(left) != len(right):
            mismatches += 1
            if len(examples) < max_examples:
                examples.append(
                    {
                        "path": path,
                        "reason": "list_length_mismatch",
                        "reference_length": len(left),
                        "candidate_length": len(right),
                    }
                )
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            mismatches += _compare_json_values(
                left_item,
                right_item,
                path=f"{path}[{index}]",
                rtol=rtol,
                atol=atol,
                examples=examples,
                max_examples=max_examples,
            )
        return mismatches
    equal = type(left) is type(right) and left == right
    if not equal and len(examples) < max_examples:
        examples.append({"path": path, "reference": left, "candidate": right})
    return 0 if equal else 1


def compare_json(
    reference: Path,
    candidate: Path,
    ignored: Iterable[str],
    *,
    rtol: float,
    atol: float,
    max_examples: int = 8,
) -> dict[str, Any]:
    ignored_keys = set(ignored)
    left = strip_json_keys(json.loads(reference.read_text(encoding="utf-8")), ignored_keys)
    right = strip_json_keys(json.loads(candidate.read_text(encoding="utf-8")), ignored_keys)
    examples: list[dict[str, Any]] = []
    mismatches = _compare_json_values(
        left,
        right,
        path="$",
        rtol=rtol,
        atol=atol,
        examples=examples,
        max_examples=max_examples,
    )
    return {
        "status": "PASS" if mismatches == 0 else "VALUE_MISMATCH",
        "mismatches": mismatches,
        "examples": examples,
    }


def matching_paths(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.glob(pattern) if path.is_file())


def excluded(relative_path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(relative_path, pattern) for pattern in patterns)


def compare_results(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    contract_path = (args.contract or root / "reproducibility" / "result_contract.json").resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    reference_root = args.reference_root.resolve()
    candidate_root = args.candidate_root.resolve()
    if reference_root == candidate_root:
        raise ValueError("Reference and candidate roots must be different directories.")
    profile_rules = contract["profiles"].get(args.profile)
    if profile_rules is None:
        raise KeyError(f"Unknown result profile: {args.profile}")

    details: list[dict[str, Any]] = []
    compared: set[str] = set()
    contract_covered: set[str] = set()
    unverified_paths: set[str] = set()
    unverified_outputs: list[dict[str, Any]] = []
    for rule in profile_rules:
        mode = rule["mode"]
        ignores = set(contract.get("ignore_json_keys", [])) | set(rule.get("ignore_json_keys", []))
        ignored_csv_columns = set(contract.get("ignore_csv_columns", [])) | set(
            rule.get("ignore_csv_columns", [])
        )
        unordered_csv_columns = dict(contract.get("unordered_delimited_csv_columns", {}))
        unordered_csv_columns.update(rule.get("unordered_delimited_csv_columns", {}))
        rule_rtol = float(rule.get("rtol", args.rtol))
        rule_atol = float(rule.get("atol", args.atol))
        excludes = rule.get("exclude", [])
        paths = [
            path
            for path in matching_paths(reference_root, rule["glob"])
            if not excluded(path.relative_to(reference_root).as_posix(), excludes)
        ]
        candidate_paths = [
            path
            for path in matching_paths(candidate_root, rule["glob"])
            if not excluded(path.relative_to(candidate_root).as_posix(), excludes)
        ]
        reference_relatives = {path.relative_to(reference_root).as_posix() for path in paths}
        candidate_relatives = {path.relative_to(candidate_root).as_posix() for path in candidate_paths}
        contract_covered.update(reference_relatives)
        contract_covered.update(candidate_relatives)
        if not paths and rule.get("required", True):
            details.append({"path": rule["glob"], "mode": mode, "status": "REFERENCE_MISSING"})
            continue
        if not paths and candidate_paths:
            if rule.get("allow_candidate_without_reference", not rule.get("required", True)):
                for relative in sorted(candidate_relatives - unverified_paths):
                    unverified_paths.add(relative)
                    unverified_outputs.append(
                        {
                            "path": relative,
                            "mode": mode,
                            "status": "SKIPPED_NO_REFERENCE",
                        }
                    )
                continue
            for relative in sorted(candidate_relatives - compared - unverified_paths):
                compared.add(relative)
                details.append({"path": relative, "mode": mode, "status": "UNEXPECTED_CANDIDATE"})
            continue
        for reference in paths:
            relative = reference.relative_to(reference_root).as_posix()
            if relative in compared:
                continue
            compared.add(relative)
            candidate = candidate_root / relative
            row: dict[str, Any] = {"path": relative, "mode": mode}
            if is_lfs_pointer(reference):
                row["status"] = "REFERENCE_LFS_POINTER"
            elif not candidate.is_file():
                row["status"] = "CANDIDATE_MISSING"
            elif is_lfs_pointer(candidate):
                row["status"] = "CANDIDATE_LFS_POINTER"
            elif mode == "csv":
                row.update(
                    compare_csv(
                        reference,
                        candidate,
                        rtol=rule_rtol,
                        atol=rule_atol,
                        key_columns=rule.get("key_columns", []),
                        ignored_columns=ignored_csv_columns,
                        unordered_delimited_columns=unordered_csv_columns,
                    )
                )
            elif mode == "json":
                row.update(
                    compare_json(
                        reference,
                        candidate,
                        ignores,
                        rtol=rule_rtol,
                        atol=rule_atol,
                    )
                )
            elif mode == "sha256":
                left_hash = sha256_file(reference)
                right_hash = sha256_file(candidate)
                row.update(
                    {
                        "reference_sha256": left_hash,
                        "candidate_sha256": right_hash,
                        "status": "PASS" if left_hash == right_hash else "HASH_MISMATCH",
                    }
                )
            else:
                raise ValueError(f"Unsupported comparison mode: {mode}")
            if mode in {"csv", "json"}:
                row["relative_tolerance"] = rule_rtol
                row["absolute_tolerance"] = rule_atol
            details.append(row)

        for relative in sorted(
            candidate_relatives - reference_relatives - compared - unverified_paths
        ):
            compared.add(relative)
            details.append({"path": relative, "mode": mode, "status": "UNEXPECTED_CANDIDATE"})

    informational_globs = tuple(contract.get("informational_output_globs", []))
    scientific_paths = sorted(
        path
        for path in candidate_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".json"}
    )
    for path in scientific_paths:
        relative = path.relative_to(candidate_root).as_posix()
        if relative in contract_covered or excluded(relative, informational_globs):
            continue
        contract_covered.add(relative)
        details.append(
            {
                "path": relative,
                "mode": path.suffix.lower().lstrip("."),
                "side": "candidate",
                "status": "UNCONTRACTED_OUTPUT",
            }
        )

    if not compared and not details and not unverified_outputs:
        details.append(
            {
                "path": None,
                "mode": None,
                "status": "NO_REFERENCE_FILES",
            }
        )

    failures = [row for row in details if row.get("status") != "PASS"]
    if failures:
        overall_status = "FAIL"
    elif unverified_outputs:
        overall_status = "PASS_WITH_UNVERIFIED"
    else:
        overall_status = "PASS"
    payload = {
        "schema_version": 1,
        "check": "scientific_result_equivalence",
        "profile": args.profile,
        "reference_root": str(reference_root),
        "candidate_root": str(candidate_root),
        "relative_tolerance": args.rtol,
        "absolute_tolerance": args.atol,
        "compared_files": len(details),
        "verification_coverage": "PARTIAL" if unverified_outputs else "COMPLETE",
        "unverified_files": len(unverified_outputs),
        "unverified_outputs": unverified_outputs,
        "failures": len(failures),
        "status": overall_status,
        "details": details if args.verbose or failures else [],
    }
    write_report(payload, args.report)
    return 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root())
    subparsers = parser.add_subparsers(dest="command", required=True)

    archive = subparsers.add_parser("archive", help="Validate the repository checksum inventory.")
    archive.add_argument("--inventory", type=Path)
    archive.add_argument("--scope", choices=("source", "workload", "core", "sensitivity", "apple", "intel", "rtl", "all"), default="all")
    archive.add_argument("--require-materialized", action="store_true")
    archive.add_argument("--report", type=Path)
    archive.add_argument("--verbose", action="store_true")
    archive.set_defaults(func=verify_archive)

    compare = subparsers.add_parser("compare", help="Compare regenerated results with the archive.")
    compare.add_argument("--reference-root", type=Path, required=True)
    compare.add_argument("--candidate-root", type=Path, required=True)
    compare.add_argument("--contract", type=Path)
    compare.add_argument(
        "--profile",
        choices=(
            "smoke", "workload", "core-paper", "core", "sensitivity-paper", "sensitivity",
            "apple-paper", "apple", "intel-paper", "intel-orders", "rtl", "all",
        ),
        required=True,
    )
    compare.add_argument("--rtol", type=float, default=1e-10)
    compare.add_argument("--atol", type=float, default=1e-12)
    compare.add_argument("--report", type=Path)
    compare.add_argument("--verbose", action="store_true")
    compare.set_defaults(func=compare_results)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
