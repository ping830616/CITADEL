from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import verify_paper_results


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = ROOT / "reproducibility" / "paper_results"


class VerifyPaperResultsTests(unittest.TestCase):
    def test_all_compact_families_pass_coverage_and_traceability(self) -> None:
        report = verify_paper_results.audit_repository(ROOT)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["coverage_status"], "PASS")
        self.assertEqual(report["traceability_status"], "PASS")
        self.assertEqual(
            set(report["families_present"]),
            set(verify_paper_results.EXPECTED_FAMILIES),
        )
        for family in report["families"].values():
            self.assertEqual(family["coverage_status"], "PASS")
            self.assertEqual(family["traceability_status"], "PASS")
            self.assertEqual(family["paper_claims_status"], "PASS")

    def test_integrity_pass_does_not_overstate_fresh_clean_evidence(self) -> None:
        report = verify_paper_results.audit_repository(ROOT)
        families = report["families"]
        self.assertEqual(report["fresh_clean_rerun_status"], "NOT_ESTABLISHED")
        self.assertFalse(report["all_results_fresh_clean_rerun_verified"])

        self.assertEqual(
            families["core"]["evidence_class"],
            "historical_non_archival_reference",
        )
        self.assertEqual(families["core"]["archival_status"], "REFERENCE_ONLY")
        self.assertFalse(families["core"]["fresh_clean_rerun_verified"])
        self.assertEqual(
            families["apple"]["evidence_class"],
            "historical_non_archival_reference",
        )
        self.assertFalse(families["apple"]["fresh_clean_rerun_verified"])

        self.assertEqual(families["rtl"]["evidence_class"], "archived_reanalysis")
        self.assertEqual(families["rtl"]["archival_status"], "ARCHIVED_REANALYSIS")
        self.assertFalse(families["rtl"]["fresh_clean_rerun_verified"])

        self.assertTrue(families["sensitivity"]["fresh_clean_rerun_verified"])
        self.assertTrue(families["intel"]["fresh_clean_rerun_verified"])
        self.assertEqual(len(report["fresh_clean_rerun_limitations"]), 3)

    def test_claim_audit_names_every_added_manuscript_check(self) -> None:
        report = verify_paper_results.audit_repository(ROOT)
        claim_ids = {
            family: {
                check["id"]
                for check in result["checks"]["paper_claims"]
            }
            for family, result in report["families"].items()
        }
        self.assertTrue(
            {
                "table_vi.all_reported_cells",
                "table_vii.all_reported_cells",
                "table_viii.all_reported_cells",
                "table_ix.all_reported_cells",
                "section_vf.operator_constants",
                "figure_6.lifecycle",
            }.issubset(claim_ids["core"])
        )
        self.assertIn(
            "sensitivity.stability_threshold_invariance",
            claim_ids["sensitivity"],
        )
        self.assertTrue(
            {
                "section_v_i.protocol",
                "section_v_i.persistence_reduction",
            }.issubset(claim_ids["intel"])
        )
        self.assertIn("figure_8.printed_configurations", claim_ids["apple"])

    def test_tampered_declared_output_fails_hash_and_claim_audits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle_root = Path(directory) / "paper_results"
            shutil.copytree(BUNDLE_ROOT / "core", bundle_root / "core")
            table = bundle_root / "core" / "table_x_citadel_row.csv"
            table.write_text(
                table.read_text(encoding="utf-8").replace(
                    "Fixed-point CINTAS", "altered scoring"
                ),
                encoding="utf-8",
            )

            report = verify_paper_results.audit_repository(
                ROOT,
                bundle_root=bundle_root,
                families=("core",),
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["traceability_status"], "FAIL")
            core = report["families"]["core"]
            self.assertEqual(core["paper_claims_status"], "FAIL")
            messages = [
                check["message"]
                for check in core["checks"]["traceability"]
                if check["status"] == "FAIL"
            ]
            self.assertTrue(any("sha256 mismatch" in message for message in messages))

    def test_missing_requested_family_fails_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = verify_paper_results.audit_repository(
                ROOT,
                bundle_root=Path(directory),
                families=("rtl",),
            )
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["coverage_status"], "FAIL")
        self.assertFalse(report["families"]["rtl"]["present"])

    def test_cli_can_write_a_machine_readable_partial_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "core_audit.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                return_code = verify_paper_results.main(
                    [
                        "--repo-root",
                        str(ROOT),
                        "--family",
                        "core",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(return_code, 0)
            self.assertEqual(json.loads(stdout.getvalue()), json.loads(output.read_text()))
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["families_requested"], ["core"])
            self.assertEqual(report["fresh_clean_rerun_status"], "NOT_ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
