from __future__ import annotations

import ast
import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import (
    analyze_intel_transition_campaign,
    analyze_intel_workload_orders,
    run_graph_sensitivity,
)


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReproducibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_script("citadel_reproduce", "scripts/reproduce.py")
        cls.verifier = load_script("citadel_verify", "scripts/verify_reproducibility.py")
        cls.archive_builder = load_script(
            "citadel_archive_builder", "scripts/build_archive_manifest.py"
        )

    def test_notebook_code_cells_parse(self) -> None:
        notebook = json.loads((ROOT / "notebooks/exact_tcad_all_experiments.ipynb").read_text())
        for cell in notebook["cells"]:
            if cell.get("cell_type") == "code":
                ast.parse("".join(cell.get("source", [])))

    def test_all_direct_requirements_are_exact(self) -> None:
        requirements = self.runner.direct_requirements(ROOT)
        self.assertGreaterEqual(len(requirements), 10)
        for package, version in requirements.items():
            self.assertTrue(package)
            self.assertRegex(version, r"^\d+(?:\.\d+)+(?:[A-Za-z0-9.+-]*)?$")

    def test_successful_archive_verification_returns_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tracked = root / "tracked.txt"
            tracked.write_text("archived content\n", encoding="utf-8")
            inventory = root / "archive_manifest.json"
            inventory.write_text(
                json.dumps(
                    {
                        "file_count": 1,
                        "files": [
                            {
                                "path": "tracked.txt",
                                "storage": "git",
                                "sha256": self.verifier.sha256_file(tracked),
                                "size_bytes": tracked.stat().st_size,
                                "scopes": ["source"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = root / "report.json"
            args = argparse.Namespace(
                repo_root=root,
                inventory=inventory,
                scope="source",
                require_materialized=False,
                report=report,
                verbose=False,
            )
            with mock.patch.object(
                self.verifier, "tracked_inventory_paths", return_value={"tracked.txt"}
            ), contextlib.redirect_stdout(io.StringIO()):
                returncode = self.verifier.verify_archive(args)
            self.assertEqual(returncode, 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["failures"], 0)

    def test_csv_comparison_uses_declared_numeric_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            reference.write_text("case,value\nA,0.940000000000\n", encoding="utf-8")
            candidate.write_text("case,value\nA,0.940000000001\n", encoding="utf-8")
            result = self.verifier.compare_csv(reference, candidate, rtol=1e-10, atol=1e-12)
            self.assertEqual(result["status"], "PASS")
            candidate.write_text("case,value\nB,0.94\n", encoding="utf-8")
            result = self.verifier.compare_csv(reference, candidate, rtol=1e-10, atol=1e-12)
            self.assertEqual(result["status"], "VALUE_MISMATCH")

    def test_positional_csv_stream_reports_exact_row_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            reference.write_text("case,value\nA,1\nB,2\nC,3\n", encoding="utf-8")
            candidate.write_text("case,value\nA,1\nB,2\n", encoding="utf-8")
            result = self.verifier.compare_csv(reference, candidate, rtol=0.0, atol=0.0)
            self.assertEqual(
                result,
                {
                    "status": "ROW_COUNT_MISMATCH",
                    "reference_rows": 3,
                    "candidate_rows": 2,
                },
            )

    def test_keyed_csv_comparison_is_order_independent_and_rejects_bad_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            reference.write_text("id,value\nA,1.0\nB,2.0\n", encoding="utf-8")
            candidate.write_text("id,value\nB,2.0\nA,1.0\n", encoding="utf-8")
            result = self.verifier.compare_csv(
                reference,
                candidate,
                rtol=1e-10,
                atol=1e-12,
                key_columns=("id",),
            )
            self.assertEqual(result["status"], "PASS")

            candidate.write_text("id,value\nA,1.0\nA,2.0\n", encoding="utf-8")
            result = self.verifier.compare_csv(
                reference,
                candidate,
                rtol=1e-10,
                atol=1e-12,
                key_columns=("id",),
            )
            self.assertEqual(result["status"], "DUPLICATE_KEY")

            candidate.write_text("id,value\nA,1.0\nC,2.0\n", encoding="utf-8")
            result = self.verifier.compare_csv(
                reference,
                candidate,
                rtol=1e-10,
                atol=1e-12,
                key_columns=("id",),
            )
            self.assertEqual(result["status"], "KEY_MISMATCH")
            self.assertEqual(result["missing_candidate_keys"], [["B"]])
            self.assertEqual(result["extra_candidate_keys"], [["C"]])

    def test_unordered_feature_serialization_is_compared_as_a_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.csv"
            candidate = root / "candidate.csv"
            reference.write_text("case,features\nA,alpha|beta|gamma\n", encoding="utf-8")
            candidate.write_text("case,features\nA,gamma|alpha|beta\n", encoding="utf-8")
            result = self.verifier.compare_csv(
                reference,
                candidate,
                rtol=0.0,
                atol=0.0,
                key_columns=("case",),
                unordered_delimited_columns={"features": "|"},
            )
            self.assertEqual(result["status"], "PASS")

    def test_json_comparison_uses_tolerance_but_not_for_booleans_or_strings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.json"
            candidate = root / "candidate.json"
            reference.write_text('{"value": 0.94, "enabled": true, "kind": "A"}\n')
            candidate.write_text('{"value": 0.940000000001, "enabled": true, "kind": "A"}\n')
            result = self.verifier.compare_json(
                reference,
                candidate,
                (),
                rtol=1e-10,
                atol=1e-12,
            )
            self.assertEqual(result["status"], "PASS")
            candidate.write_text('{"value": 0.94, "enabled": 1, "kind": "B"}\n')
            result = self.verifier.compare_json(
                reference,
                candidate,
                (),
                rtol=1e-10,
                atol=1e-12,
            )
            self.assertEqual(result["status"], "VALUE_MISMATCH")
            self.assertEqual(result["mismatches"], 2)

    def test_notebook_profiles_are_explicit_and_isolated(self) -> None:
        source = ROOT / "notebooks/exact_tcad_all_experiments.ipynb"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "prepared.ipynb"
            selection = self.runner.prepare_notebook(source, destination, "smoke")
            self.assertIn("258cb59d", selection["kept_cell_ids"])
            self.assertIn("2158d272", selection["skipped_cell_ids"])
            self.assertIn("7196b2df", selection["skipped_cell_ids"])
            json.loads(destination.read_text(encoding="utf-8"))

            workload_destination = Path(directory) / "prepared-workload.ipynb"
            workload_selection = self.runner.prepare_notebook(
                source, workload_destination, "workload"
            )
            self.assertIn(
                "citadel-workload-profile-analysis",
                workload_selection["kept_cell_ids"],
            )
            self.assertIn("540aa7ce", workload_selection["skipped_cell_ids"])

    def test_standalone_workload_cell_requires_a_fresh_isolated_root(self) -> None:
        notebook = json.loads(
            (ROOT / "notebooks/exact_tcad_all_experiments.ipynb").read_text(
                encoding="utf-8"
            )
        )
        source = "".join(
            next(
                cell
                for cell in notebook["cells"]
                if cell.get("id") == "citadel-workload-profile-analysis"
            )["source"]
        )
        self.assertIn("import os", source)
        self.assertIn("threadpool_info()", source)
        self.assertIn("git_status_at_start", source)
        preamble = source.split("_workload_notebook =", 1)[0]
        compile(preamble, "<standalone-workload-preamble>", "exec")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notebooks").mkdir()
            (root / "notebooks/exact_tcad_all_experiments.ipynb").write_text(
                "{}", encoding="utf-8"
            )
            (root / "data/telemetry/processed/ddr_data").mkdir(parents=True)
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.dict(
                    os.environ,
                    {
                        "CITADEL_RESULTS_ROOT": (
                            "results/reproduced/test-workload/notebook_run"
                        )
                    },
                    clear=False,
                ):
                    namespace: dict[str, object] = {}
                    exec(preamble, namespace)
                    self.assertEqual(
                        namespace["WORKLOAD_PROFILE_OUT"],
                        (
                            root
                            / "results/reproduced/test-workload/notebook_run/workload_profiles"
                        ).resolve(),
                    )
                    Path(namespace["WORKLOAD_PROFILE_OUT"]).mkdir(parents=True)
                    with self.assertRaisesRegex(FileExistsError, "already exists"):
                        exec(preamble, {})
            finally:
                os.chdir(old_cwd)

    def test_sample_smoke_run_has_no_lfs_dependency(self) -> None:
        self.assertIsNone(self.runner.notebook_lfs_scope("smoke", "sample"))
        self.assertEqual(self.runner.notebook_lfs_scope("smoke", "real"), "smoke")
        audit = self.runner.lfs_audit(ROOT, None)
        self.assertEqual(audit["status"], "NOT_REQUIRED")
        self.assertEqual(audit["matched_files"], 0)

    def test_generation_lfs_scopes_are_separate_from_archived_references(self) -> None:
        core_inputs = self.runner.lfs_patterns("core")
        core_verify = self.runner.lfs_patterns("core", include_reference=True)
        self.assertIn("data/telemetry/processed/ddr_data/*.csv", core_inputs)
        self.assertIn("results/notebook_run/rtl_sweep/rtl_resource_summary.csv", core_inputs)
        self.assertNotIn("results/notebook_run/lifecycle_drift/**/*.csv", core_inputs)
        self.assertEqual(core_verify, core_inputs)
        self.assertTrue((ROOT / "reproducibility/paper_results/core/evidence_manifest.json").is_file())

        sensitivity_inputs = self.runner.lfs_patterns("sensitivity")
        sensitivity_verify = self.runner.lfs_patterns(
            "sensitivity", include_reference=True
        )
        self.assertNotIn(
            "results/notebook_run/graph_sensitivity/*.csv", sensitivity_inputs
        )
        self.assertEqual(sensitivity_verify, sensitivity_inputs)
        self.assertTrue(
            (ROOT / "reproducibility/paper_results/sensitivity/evidence_manifest.json").is_file()
        )
        self.assertNotIn(
            "results/notebook_run/apple_limited_observability/**/*.csv",
            self.runner.lfs_patterns("apple"),
        )
        self.assertEqual(
            self.runner.lfs_patterns("apple", include_reference=True),
            self.runner.lfs_patterns("apple"),
        )
        self.assertTrue((ROOT / "reproducibility/paper_results/apple/evidence_manifest.json").is_file())

    def test_rtl_scope_matches_material_files_not_only_directories(self) -> None:
        paths = self.runner.expand_patterns(ROOT, self.runner.LFS_PATTERNS["rtl"])
        self.assertGreater(len(paths), 0)
        self.assertTrue(any(path.name == "rtl_resource_summary.csv" for path in paths))

    def test_intel_scope_and_inputs_are_exactly_the_benign_workload_set(self) -> None:
        self.assertEqual(
            self.runner.LFS_PATTERNS["intel"],
            ("data/telemetry/processed/ddr_data/*_benign_*.csv",),
        )
        paths = self.runner.intel_input_paths(ROOT)
        self.assertEqual(len(paths), 26)
        self.assertEqual(len(set(paths)), 26)
        self.assertTrue(all("_benign_" in path.name for path in paths))
        self.assertEqual(
            self.runner.LFS_PATTERNS["workload"],
            ("data/telemetry/processed/ddr_data/*_benign_*.csv",),
        )
        self.assertIn(
            "intel",
            self.archive_builder.scopes_for(
                "data/telemetry/processed/ddr_data/DDR4_benign_dft.csv"
            ),
        )
        self.assertNotIn(
            "intel",
            self.archive_builder.scopes_for(
                "data/telemetry/processed/ddr_data/DDR4_rowpress_dft.csv"
            ),
        )

    def test_workload_and_future_core_outputs_have_archive_scopes(self) -> None:
        workload_scopes = self.archive_builder.scopes_for(
            "results/notebook_run/workload_profiles/manifest.json"
        )
        self.assertIn("core", workload_scopes)
        self.assertIn("workload", workload_scopes)
        self.assertIn(
            "core",
            self.archive_builder.scopes_for(
                "results/notebook_run/paper_tbd_replacements.csv"
            ),
        )
        self.assertIn(
            "core",
            self.archive_builder.scopes_for(
                "results/notebook_run/ets_baseline/run_manifest.json"
            ),
        )

    def test_workload_profile_requires_real_data_and_repeat_not_archive_verify(self) -> None:
        self.runner.validate_notebook_request(
            profile="workload", preset="smoke", data_mode="real", verify=False
        )
        with self.assertRaisesRegex(ValueError, "preserved benign telemetry"):
            self.runner.validate_notebook_request(
                profile="workload", preset="smoke", data_mode="sample", verify=False
            )
        with self.assertRaisesRegex(ValueError, "does not contain"):
            self.runner.validate_notebook_request(
                profile="workload", preset="smoke", data_mode="real", verify=True
            )

    def test_intel_runner_exposes_repeat_and_archive_verification(self) -> None:
        args = self.runner.build_parser().parse_args(
            ["intel-orders", "--repeat", "--verify", "--run-id", "test-intel"]
        )
        self.assertTrue(args.repeat)
        self.assertTrue(args.verify)
        self.assertEqual(args.run_id, "test-intel")

        with tempfile.TemporaryDirectory() as directory:
            args.repo_root = Path(directory)
            args.repeat = False
            args.allow_dirty = False
            args.allow_runtime_mismatch = False
            with self.assertRaisesRegex(FileNotFoundError, "does not contain one"):
                self.runner.command_intel_orders(args)

    def test_intel_analyzer_requires_a_new_explicit_output(self) -> None:
        source = (ROOT / "scripts" / "analyze_intel_workload_orders.py").read_text()
        self.assertIn('"--output",\n        type=Path,\n        required=True', source)
        self.assertIn("if output.exists():", source)
        self.assertIn("scripts/reproduce.py intel-orders", source)

    def test_intel_receipt_binds_inputs_runtime_and_analyzer_manifest(self) -> None:
        source = (ROOT / "scripts" / "reproduce.py").read_text()
        for field in (
            '"clean_checkout_at_start"',
            '"environment_files"',
            '"inputs"',
            '"numerical_runtime"',
            '"notebook_utility_loader"',
            '"analyzer_run_manifest"',
        ):
            self.assertIn(field, source)
        self.assertIn("threadpool_info", source)
        self.assertIn("numpy_configuration", source)
        bound_sources = {
            path.relative_to(ROOT).as_posix()
            for path in self.runner.intel_source_paths(ROOT)
        }
        self.assertEqual(
            bound_sources,
            {
                "scripts/reproduce.py",
                "scripts/analyze_intel_workload_orders.py",
                "notebooks/exact_tcad_all_experiments.ipynb",
                "data/external_sources.json",
            },
        )
        self.assertEqual(source.count("file_inventory(root, source_paths)"), 2)
        self.assertEqual(
            self.runner.INTEL_NOTEBOOK_UTILITY_LOADER,
            analyze_intel_workload_orders.NOTEBOOK_UTILITY_LOADER,
        )
        self.assertEqual(
            self.runner.INTEL_NOTEBOOK_UTILITY_LOADER,
            analyze_intel_transition_campaign.NOTEBOOK_UTILITY_LOADER,
        )

    def test_allow_runtime_mismatch_disables_the_notebook_runtime_gate(self) -> None:
        self.assertEqual(self.runner.notebook_strict_runtime_setting(False), "1")
        self.assertEqual(self.runner.notebook_strict_runtime_setting(True), "0")

    def test_intel_utility_loaders_are_validation_free_and_restore_environment(self) -> None:
        attempted_nonbenign_reads: list[str] = []
        original_open = Path.open

        def guarded_open(path: Path, *args, **kwargs):
            if (
                path.suffix.lower() == ".csv"
                and "ddr_data" in path.parts
                and "_benign_" not in path.name.lower()
            ):
                attempted_nonbenign_reads.append(str(path))
                raise AssertionError(f"non-benign telemetry was inspected: {path}")
            return original_open(path, *args, **kwargs)

        ambient = {
            "CITADEL_SEED": "999",
            "CITADEL_THREADS": "7",
            "CITADEL_PROFILE": "all",
            "CITADEL_DATA_MODE": "real",
            "CITADEL_STRICT_RUNTIME": "1",
        }
        with mock.patch.dict(os.environ, ambient, clear=False):
            expected_environment = dict(os.environ)
            with mock.patch.object(Path, "open", guarded_open), contextlib.redirect_stdout(
                io.StringIO()
            ):
                for analyzer in (
                    analyze_intel_workload_orders,
                    analyze_intel_transition_campaign,
                ):
                    namespace = analyzer._load_notebook_namespace(ROOT)
                    self.assertEqual(namespace["NOTEBOOK_PROFILE"], "smoke")
                    self.assertEqual(namespace["DATA_MODE"], "sample")
                    self.assertEqual(namespace["SEED"], 123)
                    self.assertEqual(namespace["THREADS"], 1)
                    self.assertEqual(dict(os.environ), expected_environment)
        self.assertEqual(attempted_nonbenign_reads, [])

    def test_transition_analysis_requires_a_fresh_campaign_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fresh"
            analyze_intel_transition_campaign._create_new_output_directory(output)
            self.assertTrue(output.is_dir())
            with self.assertRaisesRegex(FileExistsError, "fresh --output-root"):
                analyze_intel_transition_campaign._create_new_output_directory(output)

    def test_smoke_archive_verification_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "smoke grid"):
            self.runner.validate_notebook_request(
                profile="smoke",
                preset="smoke",
                data_mode="sample",
                verify=True,
            )
        with self.assertRaisesRegex(ValueError, "requires --preset full"):
            self.runner.validate_notebook_request(
                profile="core",
                preset="smoke",
                data_mode="real",
                verify=True,
            )
        self.runner.validate_notebook_request(
            profile="core",
            preset="full",
            data_mode="real",
            verify=True,
        )
        with self.assertRaisesRegex(ValueError, "verify-paper --scope all"):
            self.runner.validate_notebook_request(
                profile="all",
                preset="full",
                data_mode="real",
                verify=True,
            )

    def test_verify_paper_command_is_explicitly_scoped(self) -> None:
        args = self.runner.build_parser().parse_args(
            ["verify-paper", "--scope", "sensitivity"]
        )
        self.assertEqual(args.scope, "sensitivity")
        self.assertIsNone(args.output)
        with mock.patch.object(self.runner.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(self.runner.command_verify_paper(args), 0)
        command = run.call_args.args[0]
        self.assertIn("scripts/verify_paper_results.py", command[1])
        self.assertEqual(command[-2:], ["--family", "sensitivity"])

    def test_run_ids_cannot_escape_or_reuse_the_output_directory(self) -> None:
        for unsafe in ("../escape", "/tmp/escape", "has space", ""):
            with self.assertRaises(ValueError):
                self.runner.validate_run_id(unsafe)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            created = self.runner.ensure_new_run_root(root, "safe-run_1.0")
            self.assertEqual(created, root / "results/reproduced/safe-run_1.0")
            with self.assertRaises(FileExistsError):
                self.runner.ensure_new_run_root(root, "safe-run_1.0")

    def test_repeat_root_is_rejected_before_any_expensive_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "results/reproduced/test-run-repeat").mkdir(parents=True)
            common = {
                "repo_root": root,
                "run_id": "test-run",
                "repeat": True,
                "verify": False,
                "allow_dirty": False,
                "allow_runtime_mismatch": False,
            }
            commands = (
                (
                    self.runner.command_notebook,
                    "execute_notebook",
                    argparse.Namespace(
                        **common,
                        profile="smoke",
                        preset="smoke",
                        data_mode="sample",
                    ),
                ),
                (
                    self.runner.command_sensitivity,
                    "execute_sensitivity",
                    argparse.Namespace(**common),
                ),
                (
                    self.runner.command_intel_orders,
                    "execute_intel_orders",
                    argparse.Namespace(**common),
                ),
            )
            for command, executor_name, args in commands:
                with self.subTest(command=command.__name__), mock.patch.object(
                    self.runner, executor_name
                ) as executor:
                    with self.assertRaisesRegex(FileExistsError, "test-run-repeat"):
                        command(args)
                    executor.assert_not_called()

    def test_completed_runs_reject_inflight_repository_changes(self) -> None:
        with (
            mock.patch.object(self.runner, "git_output", return_value="b" * 40),
            mock.patch.object(self.runner, "git_status", return_value=[]),
        ):
            with self.assertRaisesRegex(RuntimeError, "changed during execution"):
                self.runner.assert_repository_snapshot_unchanged(
                    ROOT,
                    repository_commit="a" * 40,
                    status_at_start=[],
                )

    @unittest.skipUnless(
        importlib.util.find_spec("nbformat") is not None
        and importlib.util.find_spec("nbclient") is not None,
        "nbclient integration test requires the locked notebook environment",
    )
    def test_nbclient_launcher_executes_a_minimal_notebook(self) -> None:
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "id": "minimal-cell",
                    "metadata": {},
                    "outputs": [],
                    "source": ["print(6 * 7)\n"],
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                }
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        compile(self.runner.NBCLIENT_LAUNCH_CODE, "<nbclient-launcher>", "exec")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ipynb"
            destination = root / "executed.ipynb"
            source.write_text(json.dumps(notebook), encoding="utf-8")
            environment = self.runner.deterministic_environment()
            environment["JUPYTER_PATH"] = str(self.runner.write_locked_kernelspec(root))
            kernel = json.loads(
                (root / "jupyter/kernels/citadel-locked/kernel.json").read_text(encoding="utf-8")
            )
            self.assertEqual(kernel["argv"][0], self.runner.sys.executable)
            completed = subprocess.run(
                self.runner.nbclient_command(source, destination, root),
                env=environment,
                timeout=60,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0 and (
                "PermissionError: [Errno 1] Operation not permitted" in completed.stderr
            ):
                self.skipTest("local sandbox prohibits the loopback socket required by Jupyter")
            completed.check_returncode()
            executed = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(executed["cells"][0]["execution_count"], 1)
            self.assertEqual(executed["cells"][0]["outputs"][0]["text"], ["42\n"])

    def test_result_comparison_reports_reference_lfs_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference"
            candidate = root / "candidate"
            reference.mkdir()
            candidate.mkdir()
            (reference / "table.csv").write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                f"oid sha256:{'a' * 64}\n"
                "size 24\n",
                encoding="utf-8",
            )
            (candidate / "table.csv").write_text("case,value\nA,0.94\n", encoding="utf-8")
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profiles": {"sensitivity": [{"glob": "*.csv", "mode": "csv"}]},
                    }
                ),
                encoding="utf-8",
            )
            report = root / "report.json"
            args = argparse.Namespace(
                repo_root=ROOT,
                contract=contract,
                reference_root=reference,
                candidate_root=candidate,
                profile="sensitivity",
                rtol=1e-10,
                atol=1e-12,
                report=report,
                verbose=False,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                status = self.verifier.compare_results(args)
            self.assertEqual(status, 1)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["details"][0]["status"], "REFERENCE_LFS_POINTER")

    def test_uncontracted_candidate_scientific_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference"
            candidate = root / "candidate"
            reference.mkdir()
            candidate.mkdir()
            (reference / "table.csv").write_text("id,value\nA,1\n", encoding="utf-8")
            (candidate / "table.csv").write_text("id,value\nA,1\n", encoding="utf-8")
            (candidate / "new_claim.csv").write_text("id,value\nB,2\n", encoding="utf-8")
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profiles": {"smoke": [{"glob": "table.csv", "mode": "csv"}]},
                    }
                ),
                encoding="utf-8",
            )
            report = root / "report.json"
            args = argparse.Namespace(
                repo_root=ROOT,
                contract=contract,
                reference_root=reference,
                candidate_root=candidate,
                profile="smoke",
                rtol=1e-10,
                atol=1e-12,
                report=report,
                verbose=False,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                status = self.verifier.compare_results(args)
            self.assertEqual(status, 1)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(
                any(item["status"] == "UNCONTRACTED_OUTPUT" for item in payload["details"])
            )

    def test_optional_candidate_only_output_is_reported_as_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference"
            candidate = root / "candidate"
            reference.mkdir()
            candidate.mkdir()
            (candidate / "optional.csv").write_text("id,value\nA,1\n", encoding="utf-8")
            contract = root / "contract.json"
            contract.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profiles": {
                            "smoke": [
                                {
                                    "glob": "optional.csv",
                                    "mode": "csv",
                                    "required": False,
                                },
                                {
                                    "glob": "*.csv",
                                    "mode": "csv",
                                    "required": False,
                                    "allow_candidate_without_reference": False,
                                },
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = root / "report.json"
            args = argparse.Namespace(
                repo_root=ROOT,
                contract=contract,
                reference_root=reference,
                candidate_root=candidate,
                profile="smoke",
                rtol=1e-10,
                atol=1e-12,
                report=report,
                verbose=False,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                status = self.verifier.compare_results(args)
            self.assertEqual(status, 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "PASS_WITH_UNVERIFIED")
            self.assertEqual(payload["verification_coverage"], "PARTIAL")
            self.assertEqual(payload["unverified_files"], 1)
            self.assertEqual(
                payload["unverified_outputs"],
                [
                    {
                        "path": "optional.csv",
                        "mode": "csv",
                        "status": "SKIPPED_NO_REFERENCE",
                    }
                ],
            )
            self.assertEqual(payload["details"], [])

    def test_result_contract_has_every_public_profile(self) -> None:
        contract = json.loads(
            (ROOT / "reproducibility" / "result_contract.json").read_text(encoding="utf-8")
        )
        self.assertEqual(contract["schema_version"], 1)
        self.assertTrue(
            {
                "smoke", "workload", "core-paper", "core", "sensitivity",
                "apple-paper", "apple", "intel-paper", "intel-orders", "rtl", "all",
            }
            <= set(contract["profiles"])
        )
        self.assertEqual(
            contract["profiles"]["workload"],
            [{"glob": "workload_profiles/*.csv", "mode": "csv"}],
        )
        self.assertIn(
            "paper_results/**/*.csv",
            contract["informational_output_globs"],
        )
        for profile in ("core", "all"):
            rules = contract["profiles"][profile]
            self.assertNotIn(
                "fpga/cintas_setupA_q18_golden_vectors.csv",
                {rule["glob"] for rule in rules},
            )
            self.assertIn(
                {"glob": "lifecycle_drift/**/*.csv", "mode": "csv"},
                rules,
            )
            droop_data_rule = next(rule for rule in rules if rule["glob"] == "droop_adaptive_data/*.csv")
            self.assertEqual(droop_data_rule["mode"], "csv")

        intel_rules = contract["profiles"]["intel-orders"]
        summary_rule = next(
            rule
            for rule in intel_rules
            if rule["glob"] == "intel_workload_orders/intel_workload_order_summary.csv"
        )
        self.assertEqual(summary_rule["key_columns"], ["setup", "decision_rule", "metric"])
        self.assertEqual(summary_rule["rtol"], 1e-9)
        self.assertEqual(summary_rule["atol"], 5e-11)
        catch_all = next(
            rule for rule in intel_rules if rule["glob"] == "intel_workload_orders/**/*.csv"
        )
        self.assertFalse(catch_all["allow_candidate_without_reference"])
        all_intel_rules = [
            rule
            for rule in contract["profiles"]["all"]
            if rule["glob"].startswith("intel_workload_orders/")
        ]
        self.assertEqual(len(all_intel_rules), len(intel_rules))
        all_by_glob = {rule["glob"]: rule for rule in all_intel_rules}
        for dedicated_rule in intel_rules:
            all_rule = dict(all_by_glob[dedicated_rule["glob"]])
            self.assertFalse(all_rule.pop("required"))
            expected = dict(dedicated_rule)
            expected.pop("required", None)
            self.assertEqual(all_rule, expected)

    def test_graph_protocol_remains_frozen(self) -> None:
        protocol = json.loads((ROOT / "configs/graph_sensitivity.json").read_text())
        self.assertEqual(protocol["seed"], 123)
        self.assertEqual(protocol["threads"], 1)
        self.assertEqual(protocol["graph"]["setup_bootstrap_seeds"], {"A": 123, "B": 1132})
        self.assertEqual(protocol["numerical_contract"]["decision_decimals"], 9)
        self.assertEqual(
            protocol["runtime_versions"],
            self.runner.direct_requirements(ROOT),
        )
        self.assertEqual(len(protocol["cases"]), 4)

    def test_graph_decisions_quantize_native_noise_and_use_lexical_ties(self) -> None:
        notebook = json.loads((ROOT / "notebooks" / "exact_tcad_all_experiments.ipynb").read_text())
        utility = "".join(
            next(
                cell
                for cell in notebook["cells"]
                if cell.get("id") == "integrated-utilities-code"
            )["source"]
        )
        self.assertIn("GRAPH_DECISION_DECIMALS = 9", utility)
        self.assertIn("-_graph_decision_value(x[0])", utility)
        self.assertIn('["_importance_sort_score", "feature"]', utility)
        values = [(0.50000000001, "zeta"), (0.49999999999, "alpha")]
        ordered = sorted(values, key=lambda item: (-round(item[0], 9), item[1]))
        self.assertEqual([item[1] for item in ordered], ["alpha", "zeta"])

    def test_sensitivity_rejects_stale_or_missing_derived_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = [
                f"DDR4_{scenario}_{workload}.csv"
                for scenario in ("benign", "DROOP")
                for workload in run_graph_sensitivity.WORKLOAD_CODES
            ]
            for name in expected:
                (root / name).touch()
            paths = run_graph_sensitivity._require_exact_input_inventory(
                root,
                prefix="DDR4_",
                scenarios=("benign", "DROOP"),
                label="test",
            )
            self.assertEqual(len(paths), 26)
            (root / "DDR4_DROOP_stale.csv").touch()
            with self.assertRaisesRegex(RuntimeError, "unexpected"):
                run_graph_sensitivity._require_exact_input_inventory(
                    root,
                    prefix="DDR4_",
                    scenarios=("benign", "DROOP"),
                    label="test",
                )

    def test_sensitivity_rejects_inputs_changed_during_execution(self) -> None:
        started = [{"path": "input.csv", "bytes": 4, "sha256": "a" * 64}]
        finished = [{"path": "input.csv", "bytes": 4, "sha256": "b" * 64}]
        with self.assertRaisesRegex(RuntimeError, "changed during execution"):
            run_graph_sensitivity._assert_unchanged_snapshot(started, finished)

    def test_sensitivity_contract_compares_ordinal_ranks(self) -> None:
        contract = json.loads(
            (ROOT / "reproducibility" / "result_contract.json").read_text(encoding="utf-8")
        )
        for profile in ("core", "sensitivity", "all"):
            rules = contract["profiles"][profile]
            selected = next(
                rule
                for rule in rules
                if rule["glob"] == "graph_sensitivity/graph_sensitivity_selected_features.csv"
            )
            ranks = next(
                rule
                for rule in rules
                if rule["glob"] == "graph_sensitivity/graph_sensitivity_feature_ranks.csv"
            )
            self.assertNotIn("selection_rank", selected.get("ignore_csv_columns", []))
            self.assertNotIn("rank", ranks.get("ignore_csv_columns", []))

    def test_sensitivity_runtime_gate_covers_python_and_all_direct_dependencies(self) -> None:
        protocol = json.loads((ROOT / "configs" / "graph_sensitivity.json").read_text())
        expected = self.runner.direct_requirements(ROOT)
        observed = dict(expected)
        observed["numpy"] = "0.0.0"
        with (
            mock.patch.object(run_graph_sensitivity, "_runtime_versions", return_value=observed),
            mock.patch.object(run_graph_sensitivity.platform, "python_version", return_value="0.0.0"),
        ):
            diagnostic = run_graph_sensitivity._check_runtime(
                protocol,
                ROOT,
                allow_mismatch=True,
            )
            self.assertEqual(set(diagnostic["expected"]), set(expected))
            self.assertIn("numpy", diagnostic["mismatches"])
            self.assertIn("python", diagnostic["mismatches"])
            with self.assertRaisesRegex(RuntimeError, "exact locked runtime"):
                run_graph_sensitivity._check_runtime(
                    protocol,
                    ROOT,
                    allow_mismatch=False,
                )

    def test_experiment_archive_scopes_also_validate_source_entries(self) -> None:
        source_entry = {"scopes": ["source"]}
        self.assertTrue(self.verifier.selected_for_scope(source_entry, "core"))
        self.assertTrue(self.verifier.selected_for_scope(source_entry, "sensitivity"))
        self.assertTrue(self.verifier.selected_for_scope(source_entry, "apple"))
        self.assertTrue(self.verifier.selected_for_scope(source_entry, "intel"))
        self.assertTrue(self.verifier.selected_for_scope(source_entry, "rtl"))


if __name__ == "__main__":
    unittest.main()
