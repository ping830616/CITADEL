from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts import build_paper_rtl_evidence


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "reproducibility" / "paper_results" / "rtl"
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


def content_sha256(path: Path) -> str:
    content = path.read_bytes()
    if content.startswith(LFS_PREFIX):
        for line in content.decode("ascii").splitlines():
            if line.startswith("oid sha256:"):
                return line.removeprefix("oid sha256:")
        raise AssertionError(f"Malformed Git LFS pointer: {path}")
    return hashlib.sha256(content).hexdigest()


class PaperRtlEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = json.loads((BUNDLE / "evidence.json").read_text(encoding="utf-8"))

    def test_bundle_is_explicitly_archived_reanalysis(self) -> None:
        self.assertEqual(self.evidence["status"], "PASS")
        self.assertEqual(self.evidence["evidence_class"], "archived_reanalysis")
        self.assertFalse(self.evidence["fresh_vivado_synthesis"])
        self.assertEqual(self.evidence["paper_items"], ["Figure 5", "Table XI"])
        self.assertEqual(set(self.evidence["checks"].values()), {"PASS", False})

    def test_table_xi_matches_the_manuscript_contract(self) -> None:
        with (BUNDLE / "table_xi.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows, list(build_paper_rtl_evidence.TABLE_XI_EXPECTED))

    def test_figure_5_source_has_all_four_paper_cases(self) -> None:
        with (BUNDLE / "figure_5_source.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(
            [row["tag"] for row in rows],
            list(build_paper_rtl_evidence.PAPER_TAG_ORDER),
        )
        self.assertTrue(all(row["timing_met"] == "True" for row in rows))
        self.assertTrue(all(row["brams"] == "0" for row in rows))
        self.assertTrue(all(row["power_confidence"] == "Low" for row in rows))
        self.assertEqual([round(float(row["luts_pct"]), 1) for row in rows], [0.6, 0.6, 0.7, 0.7])
        self.assertEqual([round(float(row["ffs_pct"]), 1) for row in rows], [0.1, 0.1, 0.1, 0.1])
        self.assertEqual([round(float(row["dsp_pct"]), 1) for row in rows], [5.1, 5.0, 5.1, 5.0])
        self.assertEqual([round(float(row["iob_pct"]), 1) for row in rows], [73.5] * 4)

    def test_figure_5_render_is_decodable_and_composition_is_recorded(self) -> None:
        figure = BUNDLE / "figure_5.png"
        with Image.open(figure) as opened:
            width, height = opened.size
            opened.verify()
        self.assertGreaterEqual(width, 1000)
        self.assertGreaterEqual(height, 900)
        validation = self.evidence["rendered_figure"]
        self.assertTrue(validation["decoded_png"])
        self.assertTrue(validation["nonuniform"])
        self.assertEqual(
            validation["composition"],
            "timing_slack_panel_plus_four_case_resource_summary",
        )
        self.assertTrue(validation["separate_legend_present"])

    def test_every_recorded_source_and_output_hash_resolves(self) -> None:
        for record in self.evidence["sources"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertEqual(content_sha256(path), record["sha256"], record["path"])

        generator = self.evidence["generator"]
        self.assertEqual(content_sha256(ROOT / generator["path"]), generator["sha256"])
        for record in self.evidence["outputs"]:
            path = BUNDLE / record["path"]
            self.assertEqual(content_sha256(path), record["sha256"], record["path"])

    def test_bundle_rebuilds_exactly_when_rtl_lfs_inputs_are_materialized(self) -> None:
        material_inputs = [
            build_paper_rtl_evidence.ARCHIVED_SUMMARY,
            *(
                build_paper_rtl_evidence.ARCHIVED_ROOT / tag / filename
                for tag in build_paper_rtl_evidence.PAPER_TAG_ORDER
                for filename in build_paper_rtl_evidence.parse_vivado_rtl_sweep.REPORT_FILENAMES
            ),
        ]
        if any(
            build_paper_rtl_evidence.parse_vivado_rtl_sweep.is_lfs_pointer(path)
            for path in material_inputs
        ):
            self.skipTest("RTL Git LFS inputs are intentionally not materialized")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_paper_rtl_evidence.build_bundle(output)
            for filename in ("table_xi.csv", "figure_5_source.csv"):
                self.assertEqual((output / filename).read_bytes(), (BUNDLE / filename).read_bytes())
            candidate = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(
                build_paper_rtl_evidence.portable_evidence(candidate),
                build_paper_rtl_evidence.portable_evidence(self.evidence),
            )
            self.assertTrue(build_paper_rtl_evidence.figure_validation(output / "figure_5.png")["decoded_png"])


if __name__ == "__main__":
    unittest.main()
