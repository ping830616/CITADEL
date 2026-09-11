from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from scripts import (
    analyze_apple_transition_campaign,
    parse_vivado_rtl_sweep,
    run_apple_transition_analysis,
)


ROOT = Path(__file__).resolve().parents[1]


class PortabilityContractTests(unittest.TestCase):
    def test_external_source_refs_are_full_commits(self) -> None:
        registry = json.loads((ROOT / "data" / "external_sources.json").read_text())
        for source in registry.values():
            self.assertRegex(source["ref"], r"^[0-9a-f]{40}$")
        self.assertEqual(
            registry["apple_data"]["ref"],
            "b5e382e127e5ed3a187f6d328ab95729500ad7ae",
        )

    def test_notebook_manifests_bind_lock_and_numerical_runtime(self) -> None:
        notebook = json.loads(
            (ROOT / "notebooks" / "exact_tcad_all_experiments.ipynb").read_text()
        )
        utility = "".join(
            next(
                cell
                for cell in notebook["cells"]
                if cell.get("id") == "integrated-utilities-code"
            )["source"]
        )
        for filename in (".python-version", "pyproject.toml", "uv.lock"):
            self.assertIn(filename, utility)
        self.assertIn('"numerical_runtime": numerical_runtime_info()', utility)
        self.assertIn("threadpool_info()", utility)
        self.assertIn('np.__config__.show(mode="dicts")', utility)

    def test_live_intel_collection_records_timezone_and_external_hashes(self) -> None:
        collector = (ROOT / "scripts" / "collect_intel_workload_transitions.py").read_text()
        analyzer = (ROOT / "scripts" / "analyze_intel_transition_campaign.py").read_text()
        self.assertIn('"pcm_timezone": "UTC"', collector)
        self.assertIn('"external_inputs": _external_input_provenance', collector)
        self.assertIn("ZoneInfo(pcm_timezone)", analyzer)
        self.assertNotIn("st_mtime", analyzer)

    def test_campaign_selection_does_not_depend_on_filesystem_mtime(self) -> None:
        for filename in (
            "scripts/analyze_intel_transition_campaign.py",
            "scripts/analyze_apple_transition_campaign.py",
        ):
            source = (ROOT / filename).read_text()
            self.assertNotIn("st_mtime", source)

    def test_archived_rtl_reports_match_strict_contract(self) -> None:
        report_root = ROOT / "results" / "notebook_run" / "rtl_sweep"
        rows = [
            parse_vivado_rtl_sweep.parse_folder(report_root / tag)
            for tag in parse_vivado_rtl_sweep.EXPECTED_TAGS
        ]
        failures = parse_vivado_rtl_sweep.validate_rows(
            rows,
            expected_part=parse_vivado_rtl_sweep.EXPECTED_PART,
            expected_tool_prefix=parse_vivado_rtl_sweep.EXPECTED_TOOL_PREFIX,
        )
        self.assertEqual(failures, [])

    def test_apple_transition_utility_loader_is_isolated_and_restores_environment(self) -> None:
        keys = run_apple_transition_analysis.NOTEBOOK_ENVIRONMENT_KEYS
        original = {name: os.environ.get(name) for name in keys}
        hostile = {
            "CITADEL_SEED": "999",
            "CITADEL_THREADS": "16",
            "CITADEL_STRICT_RUNTIME": "1",
            "CITADEL_SAMPLE_ROWS": "-1",
        }
        os.environ.update(hostile)
        before = {name: os.environ.get(name) for name in keys}
        try:
            with tempfile.TemporaryDirectory() as directory:
                temporary = Path(directory)
                trace = temporary / "transition_trace.csv"
                output = temporary / "analysis"
                trace.write_text("idx,value\n0,1\n", encoding="utf-8")
                with run_apple_transition_analysis._isolated_notebook_utility_environment(
                    ROOT,
                    trace=trace,
                    output=output,
                    calibration_cycles=2,
                ):
                    self.assertEqual(os.environ["CITADEL_SEED"], "123")
                    self.assertEqual(os.environ["CITADEL_THREADS"], "1")
                    self.assertEqual(os.environ["CITADEL_STRICT_RUNTIME"], "0")
                    self.assertEqual(os.environ["CITADEL_PROFILE"], "smoke")
                    self.assertEqual(os.environ["CITADEL_DATA_MODE"], "sample")
                    self.assertEqual(os.environ["CITADEL_SAMPLE_ROWS"], "600")
                    self.assertEqual(os.environ["CITADEL_RUN_APPLE_OBSERVABILITY"], "0")
                    self.assertEqual(os.environ["CITADEL_APPLE_TRANSITION_TRACE"], str(trace))
                    self.assertEqual(os.environ["CITADEL_APPLE_TRANSITION_OUT"], str(output))
                    result_root = Path(os.environ["CITADEL_RESULTS_ROOT"])
                    self.assertTrue(result_root.is_relative_to(ROOT / "results" / "reproduced"))
                self.assertEqual({name: os.environ.get(name) for name in keys}, before)
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_apple_transition_per_run_output_must_be_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new-analysis"
            run_apple_transition_analysis._create_fresh_output(output)
            self.assertTrue(output.is_dir())
            with self.assertRaisesRegex(FileExistsError, "--skip-per-run-analysis"):
                run_apple_transition_analysis._create_fresh_output(output)

    def test_apple_campaign_output_reuse_is_explicit_and_complete(self) -> None:
        run_results = [{"run_index": 0, "seed": 123}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "campaign"
            runs_output = analyze_apple_transition_campaign._prepare_campaign_output(
                output,
                run_results,
                skip_per_run_analysis=False,
            )
            self.assertTrue(runs_output.is_dir())
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                analyze_apple_transition_campaign._prepare_campaign_output(
                    output,
                    run_results,
                    skip_per_run_analysis=False,
                )
            with self.assertRaisesRegex(FileNotFoundError, "incomplete per-run bundle"):
                analyze_apple_transition_campaign._prepare_campaign_output(
                    output,
                    run_results,
                    skip_per_run_analysis=True,
                )

            run_output = runs_output / "run_01_seed_123"
            run_output.mkdir()
            for filename in analyze_apple_transition_campaign.PER_RUN_ARTIFACTS:
                (run_output / filename).write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                analyze_apple_transition_campaign._prepare_campaign_output(
                    output,
                    run_results,
                    skip_per_run_analysis=True,
                ),
                runs_output,
            )


if __name__ == "__main__":
    unittest.main()
