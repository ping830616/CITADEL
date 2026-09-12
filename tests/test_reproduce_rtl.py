from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import parse_vivado_rtl_sweep, render_rtl_figure5, reproduce_rtl


ROOT = Path(__file__).resolve().parents[1]


class RtlReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Fresh clones intentionally omit this ignored run root. Tests that
        # exercise the output-boundary contract still need its parent.
        reproduce_rtl.REPRODUCED_ROOT.mkdir(parents=True, exist_ok=True)

    def test_archived_configuration_matrix_is_exact(self) -> None:
        observed = [
            (
                item.tag,
                item.features,
                item.q,
                item.samples_per_block,
                item.clock_period_ns,
            )
            for item in reproduce_rtl.CONFIGURATIONS
        ]
        self.assertEqual(
            observed,
            [
                ("A_DROOP", 15, 15, 1000, "25.000"),
                ("A_RH", 20, 8, 550, "25.000"),
                ("B_DROOP", 15, 15, 200, "25.000"),
                ("B_SPECTRE", 30, 8, 700, "25.000"),
            ],
        )
        for item in reproduce_rtl.CONFIGURATIONS:
            command = reproduce_rtl.vivado_command("vivado", item, workdir=Path("/work"))
            self.assertIn(reproduce_rtl.REQUIRED_PART, command)
            self.assertEqual(command[command.index("-source") + 1], str(reproduce_rtl.TCL_SCRIPT))

    def test_exact_vivado_build_is_required(self) -> None:
        accepted = """Vivado v2025.2 (64-bit)\nSW Build 6299465 on Fri Nov 14 2025\n"""
        reproduce_rtl.require_exact_vivado_version(accepted)
        with self.assertRaisesRegex(RuntimeError, "version mismatch"):
            reproduce_rtl.require_exact_vivado_version(
                "Vivado v2025.2 (64-bit)\nSW Build 6299464 on Fri Nov 14 2025\n"
            )
        with self.assertRaisesRegex(RuntimeError, "version mismatch"):
            reproduce_rtl.require_exact_vivado_version(
                "Vivado v2025.1 (64-bit)\nSW Build 6299465 on Fri Nov 14 2025\n"
            )

    def test_metric_comparison_is_exact_for_counts_and_tolerant_for_diagnostics(self) -> None:
        tags = [item.tag for item in reproduce_rtl.CONFIGURATIONS]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            fields = ["tag", "luts", "dynamic_power_mw", "status"]

            def write(path: Path, *, lut_offset: int = 0, power_offset: float = 0.0) -> None:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    for index, tag in enumerate(tags):
                        writer.writerow(
                            {
                                "tag": tag,
                                "luts": 860 + index + lut_offset,
                                "dynamic_power_mw": 27.0 + power_offset,
                                "status": "synthesized",
                            }
                        )

            write(reference)
            write(candidate, power_offset=0.0005)
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=1e-3, atol=1e-3
            )
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(report["raw_report_byte_identity_required"])

            write(candidate, lut_offset=1)
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=1e-3, atol=1e-3
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    failure.get("field") == "luts"
                    and failure.get("comparison") == "exact integer"
                    for failure in report["failures"]
                )
            )

    def test_paper_values_must_match_manuscript_display_precision(self) -> None:
        tags = [item.tag for item in reproduce_rtl.CONFIGURATIONS]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            fields = ["tag", "wns_ns", "fmax_mhz_est", "total_power_mw"]

            def write(path: Path, *, wns: str, fmax: str, total_power: str) -> None:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    for tag in tags:
                        writer.writerow(
                            {
                                "tag": tag,
                                "wns_ns": wns,
                                "fmax_mhz_est": fmax,
                                "total_power_mw": total_power,
                            }
                        )

            write(reference, wns="2.458", fmax="44.36", total_power="158")
            write(candidate, wns="2.460", fmax="44.40", total_power="158.49")
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=1e-3, atol=1e-3
            )
            self.assertEqual(report["status"], "FAIL")
            failures = {failure.get("field"): failure for failure in report["failures"]}
            self.assertEqual(
                failures["wns_ns"]["comparison"],
                "paper display precision (3 decimal places)",
            )
            self.assertEqual(
                failures["fmax_mhz_est"]["comparison"],
                "paper display precision (2 decimal places)",
            )
            self.assertNotIn("total_power_mw", failures)

            write(candidate, wns="2.4584", fmax="44.364", total_power="158.49")
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=0.0, atol=0.0
            )
            self.assertEqual(report["status"], "PASS")

            write(candidate, wns="2.4584", fmax="44.364", total_power="158.51")
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=1.0, atol=1.0
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    failure.get("field") == "total_power_mw"
                    and failure.get("comparison")
                    == "paper display precision (0 decimal places)"
                    for failure in report["failures"]
                )
            )

    def test_figure_5_percentages_match_one_decimal_display(self) -> None:
        tags = [item.tag for item in reproduce_rtl.CONFIGURATIONS]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            fields = ["tag", "luts_pct", "ffs_pct", "dsp_pct", "iob_pct", "bram_pct"]

            def write(path: Path, values: tuple[str, str, str, str, str]) -> None:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    for tag in tags:
                        writer.writerow({"tag": tag, **dict(zip(fields[1:], values))})

            reference_values = ("0.64", "0.09", "5.14", "73.50", "0.00")
            write(reference, reference_values)
            write(candidate, ("0.60", "0.10", "5.10", "73.54", "0.04"))
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=0.0, atol=0.0
            )
            self.assertEqual(report["status"], "PASS")

            write(candidate, ("0.70", "0.10", "5.10", "73.54", "0.04"))
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=1.0, atol=1.0
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    failure.get("field") == "luts_pct"
                    and failure.get("comparison")
                    == "paper display precision (1 decimal places)"
                    for failure in report["failures"]
                )
            )

    def test_figure_5_renderer_accepts_the_archived_summary(self) -> None:
        if reproduce_rtl.is_lfs_pointer(reproduce_rtl.ARCHIVED_SUMMARY):
            self.skipTest("RTL archived summary is intentionally not materialized")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure_5.png"
            facts = render_rtl_figure5.render_figure5(
                reproduce_rtl.ARCHIVED_SUMMARY,
                output,
            )
            self.assertTrue(output.is_file())
            self.assertTrue(facts["decoded_png"])
            self.assertTrue(facts["nonuniform"])
            self.assertGreaterEqual(facts["width_px"], 1000)
            self.assertGreaterEqual(facts["height_px"], 900)

    def test_clock_period_is_exact_not_tolerance_aware(self) -> None:
        tags = [item.tag for item in reproduce_rtl.CONFIGURATIONS]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            fields = ["tag", "clock_period_ns", "wns_ns"]

            def write(path: Path, clock: str, slack: str) -> None:
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    for tag in tags:
                        writer.writerow(
                            {"tag": tag, "clock_period_ns": clock, "wns_ns": slack}
                        )

            write(reference, "25.0", "2.4000")
            write(candidate, "25.0001", "2.4005")
            report = reproduce_rtl.compare_summaries(
                reference, candidate, rtol=1e-3, atol=1e-3
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertNotIn("clock_period_ns", report["tolerant_float_fields"])
            self.assertTrue(
                any(
                    failure.get("field") == "clock_period_ns"
                    and failure.get("comparison") == "exact text"
                    for failure in report["failures"]
                )
            )

    def test_run_config_and_report_bundle_are_strict(self) -> None:
        self.assertIn("post_synth.dcp", parse_vivado_rtl_sweep.REPORT_FILENAMES)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "A_DROOP"
            folder.mkdir()
            for filename in parse_vivado_rtl_sweep.REPORT_FILENAMES:
                (folder / filename).write_bytes(b"evidence\n")

            expected = parse_vivado_rtl_sweep.expected_run_config(
                "A_DROOP", expected_part=parse_vivado_rtl_sweep.EXPECTED_PART
            )

            def write_config(row: dict[str, str], fields: list[str] | None = None) -> None:
                columns = fields or list(parse_vivado_rtl_sweep.RUN_CONFIG_FIELDS)
                with (folder / "run_config.csv").open(
                    "w", newline="", encoding="utf-8"
                ) as handle:
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerow({field: row.get(field, "") for field in columns})

            write_config(expected)
            self.assertEqual(
                parse_vivado_rtl_sweep.validate_folder_contract(
                    folder, expected_part=parse_vivado_rtl_sweep.EXPECTED_PART
                ),
                [],
            )

            for field, bad_value in {
                "tag": "B_DROOP",
                "part": "xc7a100tcsg324-1",
                "features": "14",
                "q": "14",
                "samples_per_block": "999",
                "clock_period_ns": "25.0",
            }.items():
                with self.subTest(field=field):
                    bad = dict(expected)
                    bad[field] = bad_value
                    write_config(bad)
                    failures = parse_vivado_rtl_sweep.validate_folder_contract(
                        folder, expected_part=parse_vivado_rtl_sweep.EXPECTED_PART
                    )
                    self.assertTrue(any(f"run_config.{field}" in item for item in failures))

            write_config(expected, fields=list(parse_vivado_rtl_sweep.RUN_CONFIG_FIELDS) + ["extra"])
            failures = parse_vivado_rtl_sweep.validate_folder_contract(
                folder, expected_part=parse_vivado_rtl_sweep.EXPECTED_PART
            )
            self.assertTrue(any("fields must be" in item for item in failures))

            write_config(expected)
            (folder / "post_synth.dcp").unlink()
            failures = parse_vivado_rtl_sweep.validate_folder_contract(
                folder, expected_part=parse_vivado_rtl_sweep.EXPECTED_PART
            )
            self.assertTrue(any("post_synth.dcp" in item for item in failures))

            (folder / "post_synth.dcp").write_bytes(
                parse_vivado_rtl_sweep.LFS_POINTER_PREFIX + b"\noid sha256:deadbeef\n"
            )
            failures = parse_vivado_rtl_sweep.validate_folder_contract(
                folder, expected_part=parse_vivado_rtl_sweep.EXPECTED_PART
            )
            self.assertTrue(any("Git LFS pointer: post_synth.dcp" in item for item in failures))

    def test_manifest_hashes_root_plan_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "A_DROOP"
            folder.mkdir()
            for filename in parse_vivado_rtl_sweep.REPORT_FILENAMES:
                (folder / filename).write_bytes(b"evidence\n")
            plan = root / "reproduction_plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "source_provenance": {
                            "repository_commit": "c" * 40,
                            "repository_clean": True,
                        },
                        "runtime": {"python_version": "3.11.15"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            summary = root / "rtl_resource_summary.csv"
            summary.write_text("tag\nA_DROOP\n", encoding="utf-8")
            manifest = parse_vivado_rtl_sweep.build_manifest(
                root,
                summary,
                [],
                [],
                expected_part=parse_vivado_rtl_sweep.EXPECTED_PART,
                expected_tool_prefix=parse_vivado_rtl_sweep.EXPECTED_TOOL_PREFIX,
            )
            names = {Path(item["path"]).name for item in manifest["report_files"]}
            self.assertIn("reproduction_plan.json", names)
            self.assertIn("post_synth.dcp", names)
            self.assertEqual(manifest["source_commit"], "c" * 40)
            self.assertEqual(manifest["report_bundle_commit"], "c" * 40)
            self.assertEqual(manifest["runtime"]["python_version"], "3.11.15")

    def test_dirty_checkout_fails_closed_unless_explicitly_overridden(self) -> None:
        commit = "a" * 40

        def git_output(command: list[str], **_: object) -> str:
            if command[1:3] == ["rev-parse", "HEAD"]:
                return commit + "\n"
            return " M rtl/cintas/cintas_stream.sv\n"

        with mock.patch.object(
            reproduce_rtl.subprocess, "check_output", side_effect=git_output
        ):
            with self.assertRaisesRegex(RuntimeError, "not clean"):
                reproduce_rtl.capture_source_provenance(allow_dirty=False)
            provenance = reproduce_rtl.capture_source_provenance(allow_dirty=True)
        self.assertEqual(provenance["repository_commit"], commit)
        self.assertFalse(provenance["repository_clean"])
        self.assertTrue(provenance["dirty_override_used"])
        self.assertTrue(provenance["source_files"])

    def test_final_manifest_carries_provenance_runtime_and_comparison_hash(self) -> None:
        with tempfile.TemporaryDirectory(dir=reproduce_rtl.REPRODUCED_ROOT) as directory:
            output_root = Path(directory)
            plan = output_root / "reproduction_plan.json"
            plan.write_text("{}\n", encoding="utf-8")
            comparison = output_root / "comparison_report.json"
            comparison.write_text('{"status":"PASS"}\n', encoding="utf-8")
            manifest_path = output_root / "run_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "status": "PASS",
                        "report_files": [
                            {
                                "path": plan.relative_to(ROOT).as_posix(),
                                "sha256": reproduce_rtl.sha256_file(plan),
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            source_provenance = {
                "repository_commit": "b" * 40,
                "repository_clean": True,
                "dirty_override_used": False,
                "git_status_porcelain": [],
                "source_files": [],
            }
            runtime = {"python_version": "3.11.15"}
            final_integrity_gate = {
                "status": "PASS",
                "failures": [],
                "repository_commit_at_finish": "b" * 40,
                "git_status_porcelain_at_finish": [],
                "commit_unchanged": True,
                "git_status_unchanged": True,
                "source_files_unchanged": True,
                "changed_source_files": [],
                "archived_reference": str(reproduce_rtl.ARCHIVED_SUMMARY),
                "archived_reference_sha256": "c" * 64,
                "archived_reference_unchanged": True,
            }
            reproduce_rtl.finalize_run_manifest(
                output_root,
                source_provenance=source_provenance,
                runtime=runtime,
                final_integrity_gate=final_integrity_gate,
                comparison_path=comparison,
                comparison_status="PASS",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_commit"], "b" * 40)
            self.assertEqual(manifest["source_provenance"], source_provenance)
            self.assertEqual(manifest["final_integrity_gate"], final_integrity_gate)
            self.assertTrue(manifest["archival_eligible"])
            self.assertEqual(manifest["runtime"], runtime)
            self.assertEqual(
                manifest["comparison"]["sha256"],
                reproduce_rtl.sha256_file(comparison),
            )

            reproduce_rtl.finalize_run_manifest(
                output_root,
                source_provenance=source_provenance,
                runtime=runtime,
                final_integrity_gate=final_integrity_gate,
                comparison_path=comparison,
                comparison_status="FAIL",
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(manifest["archival_eligible"])

    def test_final_snapshot_gate_checks_git_sources_and_reference(self) -> None:
        commit = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.csv"
            reference.write_text("tag,value\nA,1\n", encoding="utf-8")
            provenance = {
                "repository_commit": commit,
                "repository_clean": True,
                "dirty_override_used": False,
                "git_status_porcelain": [],
                "source_files": [
                    {
                        "path": reproduce_rtl.TCL_SCRIPT.relative_to(ROOT).as_posix(),
                        "sha256": reproduce_rtl.sha256_file(reproduce_rtl.TCL_SCRIPT),
                    }
                ],
            }

            def clean_git(command: list[str], **_: object) -> str:
                if command[1:3] == ["rev-parse", "HEAD"]:
                    return commit + "\n"
                return ""

            with mock.patch.object(
                reproduce_rtl.subprocess, "check_output", side_effect=clean_git
            ):
                gate = reproduce_rtl.require_final_snapshot_unchanged(
                    provenance,
                    reference=reference,
                    reference_sha256=reproduce_rtl.sha256_file(reference),
                )
                self.assertEqual(gate["status"], "PASS")
                self.assertTrue(gate["archived_reference_unchanged"])

                with self.assertRaisesRegex(RuntimeError, "archived reference"):
                    reproduce_rtl.require_final_snapshot_unchanged(
                        provenance,
                        reference=reference,
                        reference_sha256="0" * 64,
                    )

                original_sha256 = reproduce_rtl.sha256_file

                def changed_source_sha256(path: Path) -> str:
                    if path.resolve() == reproduce_rtl.TCL_SCRIPT.resolve():
                        return "f" * 64
                    return original_sha256(path)

                with mock.patch.object(
                    reproduce_rtl, "sha256_file", side_effect=changed_source_sha256
                ):
                    with self.assertRaisesRegex(RuntimeError, "controlling source files"):
                        reproduce_rtl.require_final_snapshot_unchanged(
                            provenance,
                            reference=reference,
                            reference_sha256=original_sha256(reference),
                        )

            def changed_git(command: list[str], **_: object) -> str:
                if command[1:3] == ["rev-parse", "HEAD"]:
                    return "d" * 40 + "\n"
                return " M rtl/cintas/cintas_stream.sv\n"

            with mock.patch.object(
                reproduce_rtl.subprocess, "check_output", side_effect=changed_git
            ):
                with self.assertRaisesRegex(RuntimeError, "HEAD, Git worktree status"):
                    reproduce_rtl.require_final_snapshot_unchanged(
                        provenance,
                        reference=reference,
                        reference_sha256=reproduce_rtl.sha256_file(reference),
                    )

    def test_dry_run_does_not_create_output_or_require_vivado(self) -> None:
        with tempfile.TemporaryDirectory(dir=reproduce_rtl.REPRODUCED_ROOT) as directory:
            output_root = Path(directory) / "new-output"
            args = argparse.Namespace(
                vivado="definitely-not-installed-vivado",
                output_root=output_root,
                reference=reproduce_rtl.ARCHIVED_SUMMARY,
                rtol=1e-3,
                atol=1e-3,
                dry_run=True,
                allow_dirty=False,
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = reproduce_rtl.execute(args)
            self.assertEqual(status, 0)
            self.assertFalse(output_root.exists())
            self.assertIn("DRY RUN", stdout.getvalue())
            self.assertEqual(stdout.getvalue().count('"tag":'), 4)

    def test_archived_directory_cannot_be_an_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "isolated"):
            reproduce_rtl.validate_output_root(reproduce_rtl.ARCHIVED_ROOT)

    def test_direct_parser_requires_fresh_nonarchival_outputs(self) -> None:
        parser = parse_vivado_rtl_sweep.build_argument_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])
        with self.assertRaisesRegex(ValueError, "immutable archived RTL root"):
            parse_vivado_rtl_sweep.validate_output_targets(
                parse_vivado_rtl_sweep.ARCHIVED_ROOT,
                parse_vivado_rtl_sweep.ARCHIVED_ROOT / "replacement.csv",
                parse_vivado_rtl_sweep.ARCHIVED_ROOT / "replacement.json",
            )
        with tempfile.TemporaryDirectory(dir=reproduce_rtl.REPRODUCED_ROOT) as directory:
            run_root = Path(directory)
            output = run_root / "summary.csv"
            manifest = run_root / "manifest.json"
            self.assertEqual(
                parse_vivado_rtl_sweep.validate_output_targets(run_root, output, manifest),
                (run_root.resolve(), output.resolve(), manifest.resolve()),
            )
            output.write_text("already exists\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                parse_vivado_rtl_sweep.validate_output_targets(run_root, output, manifest)

    def test_output_must_be_a_unique_reproduced_run(self) -> None:
        with self.assertRaisesRegex(ValueError, "uniquely named"):
            reproduce_rtl.validate_output_root(reproduce_rtl.REPRODUCED_ROOT)

    def test_reviewer_docs_do_not_restore_or_overwrite_the_rtl_archive(self) -> None:
        for relative in (
            "docs/asu_server_runbook.md",
            "docs/tcad_end_to_end_result_methodology.md",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("results/reproduced/", source)
            self.assertNotIn("git show origin/main:scripts/vivado_cintas_synth.tcl", source)
            self.assertNotIn("git add -f results/notebook_run/rtl_sweep", source)
            self.assertNotIn("rsync -avz --progress --delete", source)


if __name__ == "__main__":
    unittest.main()
