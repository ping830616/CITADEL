from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_paper_sensitivity_evidence, verify_paper_results


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "notebook_run" / "graph_sensitivity"
BUNDLE = ROOT / "reproducibility" / "paper_results" / "sensitivity"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class PaperSensitivityEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (BUNDLE / "evidence_manifest.json").read_text(encoding="utf-8")
        )
        cls.claims = json.loads(
            (BUNDLE / "section_vd_claims.json").read_text(encoding="utf-8")
        )

    def test_bundle_is_clean_archived_evidence_without_repeat_overclaim(self) -> None:
        self.assertEqual(self.manifest["evidence_class"], "clean_archived_evidence")
        self.assertEqual(self.manifest["archival_status"], "CLEAN_ARCHIVED")
        self.assertEqual(
            self.manifest["status"], "COMPLETE_CLEAN_ARCHIVED_VERIFIED"
        )
        self.assertEqual(
            self.manifest["source_commit"],
            "54b5cbf18bafc2472d4fccc65446af6c43d63b4c",
        )
        run = self.manifest["clean_run_evidence"]
        self.assertFalse(run["git_dirty_at_start"])
        self.assertEqual(run["git_status_at_start"], [])
        self.assertEqual(run["git_status_at_finish"], [])
        self.assertTrue(run["source_and_inputs_unchanged_during_run"])
        self.assertEqual(run["archival_provenance_status"], "PASS")
        self.assertEqual(run["claim_status"], "PASS")
        self.assertEqual(run["runtime_version_mismatches"], {})
        scope = self.manifest["verification_scope"]
        self.assertTrue(scope["fresh_clean_run_recorded"])
        self.assertTrue(scope["source_archive_hashes_verified"])
        self.assertTrue(scope["claims_independently_recomputed_from_summary"])
        self.assertFalse(scope["independent_repeat_recorded"])
        self.assertFalse(scope["projection_reruns_experiment"])

    def test_exact_section_vd_ranges_are_exposed(self) -> None:
        rows = read_csv(BUNDLE / "section_vd_sensitivity_ranges.csv")
        self.assertEqual(len(rows), 6)
        observed = {
            (row["study_family"], row["metric"]): (
                row["minimum_display"],
                row["maximum_display"],
            )
            for row in rows
        }
        self.assertEqual(
            observed,
            {
                ("graph_parameter", "mcc"): ("0.940", "0.992"),
                ("graph_parameter", "fpr"): ("0.77", "1.71"),
                ("graph_parameter", "feature_jaccard"): ("37.9", "100.0"),
                ("ranking_term", "mcc"): ("0.798", "0.992"),
                ("ranking_term", "fpr"): ("0.77", "1.64"),
                ("ranking_term", "feature_jaccard"): ("53.8", "100.0"),
            },
        )
        self.assertTrue(
            all(row["matches_paper_at_reported_precision"] == "True" for row in rows)
        )
        self.assertEqual(
            sum(int(row["variant_rows"]) for row in rows if row["metric"] == "mcc"),
            36,
        )

    def test_largest_reduction_statements_trace_to_all_four_cases(self) -> None:
        rows = read_csv(BUNDLE / "section_vd_ranking_reductions.csv")
        self.assertEqual([row["case_id"] for row in rows], list(build_paper_sensitivity_evidence.CASE_ORDER))
        by_case = {row["case_id"]: row for row in rows}
        self.assertEqual(by_case["A_DROOP"]["paper_claim_variant"], "remove_centrality")
        self.assertEqual(by_case["A_RH"]["paper_claim_variant"], "remove_alignment")
        self.assertEqual(by_case["A_DROOP"]["matches_paper_claim"], "True")
        self.assertEqual(by_case["A_RH"]["matches_paper_claim"], "True")
        self.assertEqual(by_case["B_DROOP"]["paper_claim_applies"], "False")
        self.assertEqual(by_case["B_SPECTRE"]["paper_claim_applies"], "False")
        self.assertEqual(self.claims["status"], "PASS")

    def test_stability_threshold_preserves_named_decision_metrics(self) -> None:
        claim = self.claims["stability_threshold_invariance"]
        self.assertEqual(
            claim["claim"],
            "Changing the stability threshold preserved the decision metrics "
            "across the tested interval.",
        )
        self.assertEqual(claim["parameter"]["name"], "pi_min")
        self.assertEqual(claim["parameter"]["baseline"], 0.5)
        self.assertEqual(
            claim["parameter"]["tested_values"], [0.375, 0.5, 0.625]
        )
        self.assertEqual(
            claim["parameter"]["tested_interval"], [0.375, 0.625]
        )
        self.assertEqual(
            claim["parameter"]["changed_values_compared_to_baseline"],
            [0.375, 0.625],
        )
        self.assertEqual(claim["parameter"]["tau_c_held_fixed"], 0.35)
        self.assertEqual(
            [metric["name"] for metric in claim["decision_metrics"]],
            ["mcc", "fpr"],
        )
        self.assertEqual(
            [metric["meaning"] for metric in claim["decision_metrics"]],
            ["Matthews correlation coefficient", "benign false-positive rate"],
        )
        self.assertEqual(claim["scope"]["expected_comparisons"], 8)
        self.assertEqual(claim["scope"]["observed_comparisons"], 8)
        self.assertTrue(claim["all_csv_decimal_text_identical"])
        self.assertTrue(claim["all_numeric_values_strictly_equal"])
        self.assertTrue(claim["all_within_declared_tolerance"])
        self.assertTrue(claim["all_equal_at_reported_precision"])
        self.assertTrue(claim["claim_supported"])

    def test_stability_threshold_policy_is_explicit_and_not_overbroad(self) -> None:
        claim = self.claims["stability_threshold_invariance"]
        tolerance = claim["comparison_policy"]["numeric_tolerance"]
        self.assertEqual(tolerance["relative_tolerance"], 0.0)
        self.assertEqual(tolerance["absolute_tolerance"], 1e-15)
        self.assertEqual(tolerance["implementation"], "Python math.isclose")
        self.assertFalse(
            claim["comparison_policy"]["reported_precision_secondary_check"][
                "used_as_claim_gate"
            ]
        )
        excluded = claim["scope"]["excluded_from_decision_metric_claim"]
        self.assertEqual([item["metric"] for item in excluded], ["feature_jaccard"])
        self.assertIn("A_RH", excluded[0]["reason"])
        self.assertIn("pi_min=0.625", excluded[0]["reason"])

    def test_source_summary_confirms_excluded_feature_overlap_changed(self) -> None:
        summary_path = SOURCE / "graph_sensitivity_summary.csv"
        if verify_paper_results._content_identity(summary_path)[2]:
            self.skipTest(
                "Sensitivity source summary is intentionally an unfetched Git LFS object"
            )
        summary = read_csv(summary_path)
        baseline = next(
            row
            for row in summary
            if row["case_id"] == "A_RH"
            and row["experiment_family"] == "graph_parameter"
            and row["variant"] == "baseline"
        )
        changed = next(
            row
            for row in summary
            if row["case_id"] == "A_RH"
            and row["experiment_family"] == "graph_parameter"
            and row["variant"] == "pi_min_0.625"
        )
        self.assertNotEqual(
            float(changed["feature_jaccard"]),
            float(baseline["feature_jaccard"]),
        )

    def test_stability_threshold_csv_has_complete_zero_delta_comparisons(self) -> None:
        rows = read_csv(
            BUNDLE / "section_vd_stability_threshold_invariance.csv"
        )
        self.assertEqual(len(rows), 8)
        self.assertEqual(
            {(row["case_id"], row["compared_pi_min"]) for row in rows},
            {
                (case_id, pi_min)
                for case_id in build_paper_sensitivity_evidence.CASE_ORDER
                for pi_min in ("0.375", "0.625")
            },
        )
        for row in rows:
            self.assertEqual(float(row["mcc_delta_raw"]), 0.0)
            self.assertEqual(float(row["fpr_delta_raw"]), 0.0)
            for field in (
                "mcc_csv_decimal_text_identical",
                "mcc_numeric_strictly_equal",
                "mcc_within_declared_tolerance",
                "mcc_equal_at_reported_precision",
                "fpr_csv_decimal_text_identical",
                "fpr_numeric_strictly_equal",
                "fpr_within_declared_tolerance",
                "fpr_equal_at_reported_precision",
                "all_decision_metrics_csv_decimal_text_identical",
                "all_decision_metrics_numeric_strictly_equal",
                "all_decision_metrics_within_declared_tolerance",
                "all_decision_metrics_equal_at_reported_precision",
            ):
                self.assertEqual(row[field], "True", f"{row['case_id']}:{field}")

    def test_all_source_and_output_hashes_resolve(self) -> None:
        for record in self.manifest["source_files"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            identity, logical_size, _is_lfs_pointer = (
                verify_paper_results._content_identity(path)
            )
            self.assertEqual(logical_size, record["size_bytes"], record["path"])
            self.assertEqual(identity, record["sha256"], record["path"])
        for record in self.manifest["outputs"]:
            path = BUNDLE / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(path.stat().st_size, record["size_bytes"])
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), record["sha256"]
            )
        self.assertEqual(
            self.manifest["claim_audit"]["sha256"],
            hashlib.sha256(
                (BUNDLE / "section_vd_claims.json").read_bytes()
            ).hexdigest(),
        )

    def test_builder_is_byte_deterministic_and_tracked_bundle_is_current(self) -> None:
        pointer_paths = [
            record["path"]
            for record in self.manifest["source_files"]
            if verify_paper_results._content_identity(ROOT / record["path"])[2]
        ]
        if pointer_paths:
            self.skipTest(
                "Sensitivity source archive is intentionally not materialized: "
                + ", ".join(pointer_paths)
            )
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "sensitivity"
            build_paper_sensitivity_evidence.build_bundle(SOURCE, candidate)
            for name in build_paper_sensitivity_evidence.OUTPUT_FILES:
                self.assertEqual(
                    (candidate / name).read_bytes(),
                    (BUNDLE / name).read_bytes(),
                    name,
                )
        build_paper_sensitivity_evidence.check_bundle(SOURCE, BUNDLE)

    def test_claims_are_independently_recomputed_from_summary(self) -> None:
        summary_path = SOURCE / "graph_sensitivity_summary.csv"
        if verify_paper_results._content_identity(summary_path)[2]:
            self.skipTest(
                "Sensitivity source summary is intentionally an unfetched Git LFS object"
            )
        source_claims = json.loads(
            (SOURCE / "graph_sensitivity_claims.json").read_text(encoding="utf-8")
        )
        summary = read_csv(summary_path)
        self.assertEqual(
            build_paper_sensitivity_evidence.calculate_ranges(summary, source_claims),
            self.claims["ranges"],
        )
        self.assertEqual(
            build_paper_sensitivity_evidence.calculate_ranking_reductions(
                summary, source_claims
            ),
            self.claims["ranking_largest_mcc_reductions"],
        )
        protocol = json.loads(
            (SOURCE / "protocol.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            build_paper_sensitivity_evidence.calculate_stability_threshold_invariance(
                summary,
                source_claims,
                protocol,
            ),
            self.claims["stability_threshold_invariance"],
        )


if __name__ == "__main__":
    unittest.main()
