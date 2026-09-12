from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts import build_intel_paper_evidence, reproduce, verify_reproducibility


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "reproducibility" / "paper_results" / "intel"


class PaperIntelEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (BUNDLE / "evidence_manifest.json").read_text(encoding="utf-8")
        )
        cls.claims = json.loads(
            (BUNDLE / "figure7_claims.json").read_text(encoding="utf-8")
        )

    def test_bundle_records_two_clean_unchanged_runs(self) -> None:
        self.assertEqual(
            self.manifest["status"], "COMPLETE_CLEAN_REPEAT_VERIFIED"
        )
        self.assertRegex(self.manifest["source_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(self.manifest["paper_items"], ["Figure 7", "Section V-I numerical statement"])
        for run in self.manifest["clean_run_evidence"].values():
            self.assertTrue(run["clean_checkout_at_start"])
            self.assertTrue(run["repository_snapshot_unchanged_during_run"])
            self.assertEqual(run["git_status_at_finish"], [])

    def test_complete_repeat_comparison_passed(self) -> None:
        repeated = self.manifest["repeat_verification"]
        self.assertEqual(repeated["status"], "PASS")
        self.assertEqual(repeated["verification_coverage"], "COMPLETE")
        self.assertEqual(repeated["compared_files"], 166)
        self.assertEqual(repeated["failures"], 0)
        self.assertEqual(repeated["unverified_files"], 0)

    def test_paper_claims_trace_to_summary_at_reported_precision(self) -> None:
        observed = build_intel_paper_evidence.claim_audit(
            BUNDLE
            / "intel_workload_orders"
            / "intel_workload_order_summary.csv"
        )
        self.assertEqual(observed, self.claims)
        self.assertEqual(observed["status"], "PASS")
        by_setup = {item["setup"]: item for item in observed["claims"]}
        self.assertEqual(by_setup["A"]["paper_mean_percent"], "0.58")
        self.assertEqual(
            by_setup["A"]["paper_sample_sd_percentage_points"], "0.82"
        )
        self.assertEqual(by_setup["B"]["paper_mean_percent"], "0.83")
        self.assertEqual(
            by_setup["B"]["paper_sample_sd_percentage_points"], "1.00"
        )
        self.assertEqual(by_setup["A"]["paper_boundary_mean_percent"], "0.26")
        self.assertEqual(by_setup["B"]["paper_boundary_mean_percent"], "0.51")
        self.assertEqual(by_setup["A"]["paper_later_mean_percent"], "0.68")
        self.assertEqual(by_setup["B"]["paper_later_mean_percent"], "0.94")

    def test_section_v_i_protocol_traces_to_analyzer_run_and_result_rows(self) -> None:
        source = (
            ROOT
            / "results"
            / "reproduced"
            / "figure7-clean-reference"
            / "notebook_run"
            / "intel_workload_orders"
        )
        observed = build_intel_paper_evidence.paper_protocol(
            source / "run_manifest.json",
            source / "intel_workload_order_run_results.csv",
        )
        self.assertEqual(observed, self.manifest["paper_protocol"])
        self.assertEqual(
            observed,
            {
                "setups": ["A", "B"],
                "selected_features": 8,
                "block_length": 50,
                "aggregation": "mean",
                "weighting": "uniform",
                "score_mixture": 0.5,
                "replicates_per_setup": 10,
                "calibration_blocks_per_replicate": 104,
                "evaluation_blocks_per_replicate": 156,
                "calibration_threshold_rank": 104,
                "threshold_rule": "finite_sample_upper_rank_with_strict_exceedance",
                "persistence_blocks": 2,
            },
        )

    def test_two_block_persistence_reduces_each_reported_fpr_summary(self) -> None:
        summary_path = (
            BUNDLE
            / "intel_workload_orders"
            / "intel_workload_order_summary.csv"
        )
        with summary_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        means = {
            (row["setup"], row["decision_rule"], row["metric"]): float(row["mean"])
            for row in rows
        }
        for setup in ("A", "B"):
            for metric in (
                "overall_benign_fpr",
                "boundary_block_fpr",
                "within_phase_fpr",
            ):
                self.assertLess(
                    means[(setup, "persistence", metric)],
                    means[(setup, "current", metric)],
                )

    def test_every_archived_artifact_hash_and_figure_signature_resolves(self) -> None:
        for record in self.manifest["archived_artifacts"]:
            path = BUNDLE / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(path.stat().st_size, record["size_bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                record["sha256"],
            )
        figure = (
            BUNDLE
            / "intel_workload_orders"
            / "fig_intel_workload_order_variation.png"
        )
        self.assertGreater(figure.stat().st_size, 0)
        self.assertTrue(figure.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(figure) as opened:
            width, height = opened.size
            opened.verify()
        self.assertGreater(height, width)
        self.assertGreaterEqual(width, 900)
        self.assertGreaterEqual(height, 1800)
        validation = self.manifest["figure_validation"]
        self.assertTrue(validation["decoded_png"])
        self.assertTrue(validation["nonuniform"])
        self.assertEqual(validation["layout"], "three_vertical_panels")

    def test_paper_profile_and_claim_verifier_accept_the_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            candidate = temporary / "candidate"
            shutil.copytree(BUNDLE / "intel_workload_orders", candidate / "intel_workload_orders")
            report = temporary / "comparison.json"
            args = argparse.Namespace(
                repo_root=ROOT,
                contract=None,
                reference_root=BUNDLE,
                candidate_root=candidate,
                profile="intel-paper",
                rtol=1e-10,
                atol=1e-12,
                report=report,
                verbose=False,
            )
            self.assertEqual(verify_reproducibility.compare_results(args), 0)
            comparison = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(comparison["status"], "PASS")
            self.assertEqual(comparison["verification_coverage"], "COMPLETE")
            self.assertEqual(comparison["compared_files"], 2)

            claim_report = temporary / "claims.json"
            reproduce.verify_intel_paper_claims(BUNDLE, candidate, claim_report)
            self.assertEqual(
                json.loads(claim_report.read_text(encoding="utf-8"))["status"],
                "PASS",
            )


if __name__ == "__main__":
    unittest.main()
