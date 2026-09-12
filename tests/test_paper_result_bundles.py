from __future__ import annotations

import csv
import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = ROOT / "reproducibility" / "paper_results"


def load_builder():
    path = ROOT / "scripts" / "build_paper_result_bundles.py"
    spec = importlib.util.spec_from_file_location("citadel_paper_results", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class PaperResultBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()

    def test_bundle_inventory_is_explicit(self) -> None:
        core_files = {path.name for path in (BUNDLE_ROOT / "core").iterdir() if path.is_file()}
        apple_files = {path.name for path in (BUNDLE_ROOT / "apple").iterdir() if path.is_file()}
        self.assertEqual(core_files, set(self.builder.CORE_OUTPUTS))
        self.assertEqual(apple_files, set(self.builder.APPLE_OUTPUTS))

        contract = json.loads(
            (ROOT / "reproducibility" / "result_contract.json").read_text(encoding="utf-8")
        )
        self.assertEqual(contract["profiles"]["core-paper"][0]["glob"], "core/*.csv")
        self.assertEqual(contract["profiles"]["apple-paper"][0]["glob"], "apple/*.csv")

    def test_core_projected_tables_match_paper_values(self) -> None:
        selected = read_rows(BUNDLE_ROOT / "core" / "table_vi_selected_configurations.csv")
        self.assertEqual(len(selected), 4)
        self.assertEqual(
            [(row["setup"], row["event"], int(row["selected_features"])) for row in selected],
            [("A", "DROOP", 15), ("A", "RH", 20), ("B", "DROOP", 15), ("B", "SPECTRE", 30)],
        )
        self.assertEqual([round(float(row["mcc"]), 3) for row in selected], [0.992, 0.992, 0.991, 0.989])
        self.assertEqual(
            [round(100.0 * float(row["fpr"]), 2) for row in selected],
            [0.78, 0.85, 0.77, 1.10],
        )
        self.assertEqual(
            [
                (
                    row["view"],
                    int(row["available_channels"]),
                    round(float(row["retained_percent"]), 1),
                    int(row["block_length"]),
                    row["aggregation"],
                    float(row["score_mixture"]),
                    row["weighting"],
                    int(row["fixed_point_q"]),
                    float(row["threshold_quantile"]),
                    round(float(row["roc_auc"]), 3),
                    round(float(row["auc_pr"]), 3),
                    round(float(row["f1"]), 3),
                    round(float(row["area_overhead_percent"]), 3),
                    round(float(row["idle_power_overhead_percent"]), 3),
                )
                for row in selected
            ],
            [
                ("Transient", 181, 8.3, 1000, "median", 0.0, "inverse", 15, 0.99, 1.000, 1.000, 0.996, 0.083, 0.060),
                ("Standard", 181, 11.0, 550, "median", 1.0, "uniform", 8, 0.99, 1.000, 1.000, 0.996, 0.110, 0.080),
                ("Transient", 460, 3.3, 200, "median", 0.5, "inverse", 15, 0.99, 0.999, 0.999, 0.995, 0.083, 0.060),
                ("Standard", 460, 6.5, 700, "median", 0.75, "uniform", 8, 0.99, 1.000, 1.000, 0.995, 0.161, 0.118),
            ],
        )

        budgets = read_rows(BUNDLE_ROOT / "core" / "table_vii_feature_budget_tradeoff.csv")
        self.assertEqual(
            [
                (
                    int(row["minimum_budget"]),
                    int(row["maximum_budget"]),
                    int(row["saturation_budget"]),
                    round(float(row["mcc_at_minimum_budget"]), 3),
                    round(float(row["mcc_at_saturation_budget"]), 3),
                    round(float(row["mcc_at_maximum_budget"]), 3),
                    round(float(row["area_at_saturation_percent"]), 3),
                    round(float(row["power_at_saturation_percent"]), 3),
                    round(float(row["area_at_maximum_percent"]), 3),
                    round(float(row["power_at_maximum_percent"]), 3),
                )
                for row in budgets
            ],
            [
                (15, 50, 15, 0.992, 0.992, 0.597, 0.083, 0.060, 0.268, 0.197),
                (5, 30, 20, 0.180, 0.992, 0.991, 0.110, 0.080, 0.161, 0.118),
                (15, 50, 15, 0.991, 0.991, 0.989, 0.083, 0.060, 0.267, 0.196),
                (5, 30, 5, 0.986, 0.986, 0.989, 0.030, 0.021, 0.161, 0.118),
            ],
        )

        fixed_point = read_rows(BUNDLE_ROOT / "core" / "table_viii_integer_reference_error.csv")
        self.assertEqual(
            [
                (
                    int(row["fixed_point_q"]),
                    row["view"],
                    int(row["observations_compared"]),
                )
                for row in fixed_point
            ],
            [(15, "Transient", 5000), (8, "Standard", 5000), (15, "Transient", 5000), (8, "Standard", 5000)],
        )
        self.assertEqual(
            [
                f"{float(fixed_point[0]['mean_absolute_score_error']):.1e}",
                f"{float(fixed_point[0]['maximum_absolute_score_error']):.1e}",
                f"{float(fixed_point[1]['mean_absolute_score_error']):.2e}",
                f"{float(fixed_point[1]['maximum_absolute_score_error']):.2e}",
                f"{float(fixed_point[2]['mean_absolute_score_error']):.2e}",
                f"{float(fixed_point[2]['maximum_absolute_score_error']):.2e}",
                f"{float(fixed_point[3]['mean_absolute_score_error']):.2e}",
                f"{float(fixed_point[3]['maximum_absolute_score_error']):.2f}",
            ],
            ["4.6e-05", "2.6e-04", "3.74e-02", "4.78e-02", "3.88e-04", "4.89e-03", "1.14e-01", "2.09"],
        )

        cost = read_rows(BUNDLE_ROOT / "core" / "table_ix_analytical_cost.csv")
        self.assertEqual(
            [(int(row["adders"]), int(row["multipliers"]), int(row["serial_cycles"])) for row in cost],
            [(28, 32, 148), (39, 42, 201), (28, 32, 148), (57, 62, 295)],
        )
        self.assertEqual(
            [round(float(row["feature_reduction_percent"]), 1) for row in cost],
            [91.7, 89.0, 96.7, 93.5],
        )
        self.assertEqual(
            [
                (
                    int(row["selected_features"]),
                    round(float(row["area_overhead_percent"]), 3),
                    round(float(row["idle_power_overhead_percent"]), 3),
                )
                for row in cost
            ],
            [(15, 0.083, 0.060), (20, 0.110, 0.080), (15, 0.083, 0.060), (30, 0.161, 0.118)],
        )

        constants = read_rows(BUNDLE_ROOT / "core" / "section_vf_operator_constants.csv")
        self.assertEqual([row["operator"] for row in constants], ["add", "mult"])
        self.assertEqual([int(row["bit_width"]) for row in constants], [16, 16])
        self.assertEqual(
            [f"{float(row['area_mm2']):.3e}" for row in constants],
            ["1.165e-03", "4.532e-03"],
        )
        self.assertEqual(
            [row["power_mw_at_1ghz"] for row in constants],
            ["0.178", "0.5146"],
        )
        self.assertEqual([int(row["cycles"]) for row in constants], [3, 2])
        self.assertEqual([float(row["delay_ps"]) for row in constants], [62.7, 29.09])

        basis = read_rows(BUNDLE_ROOT / "core" / "section_vf_cost_basis.csv")
        self.assertEqual(
            basis,
            [{
                "operator_bit_width": "16",
                "area_normalization_mm2": "215.25",
                "idle_power_normalization_w": "35.5",
            }],
        )

        comparison = read_rows(BUNDLE_ROOT / "core" / "table_x_citadel_row.csv")
        self.assertEqual(len(comparison), 1)
        self.assertEqual(int(comparison[0]["minimum_runtime_features"]), 15)
        self.assertEqual(int(comparison[0]["maximum_runtime_features"]), 30)
        self.assertAlmostEqual(float(comparison[0]["maximum_area_overhead_percent"]), 0.16139953821138212)

    def test_core_figure_sources_cover_the_plotted_results(self) -> None:
        envelope = read_rows(BUNDLE_ROOT / "core" / "figure_3_dse_envelope.csv")
        self.assertEqual(len(envelope), 270)
        marked = [row for row in envelope if row["selected_configuration"] == "1"]
        self.assertEqual(
            [
                (row["setup"], row["event"], int(row["feature_budget"]), int(row["block_length"]))
                for row in marked
            ],
            [("A", "DROOP", 15, 1000), ("A", "RH", 20, 550), ("B", "DROOP", 15, 200), ("B", "SPECTRE", 30, 700)],
        )

        graph_nodes = read_rows(BUNDLE_ROOT / "core" / "figure_4_graph_nodes.csv")
        graph_edges = read_rows(BUNDLE_ROOT / "core" / "figure_4_graph_edges.csv")
        self.assertEqual(len(graph_nodes), 272)
        self.assertEqual(len(graph_edges), 383)
        self.assertEqual({row["setup"] for row in graph_nodes}, {"A", "B"})

        lifecycle = read_rows(BUNDLE_ROOT / "core" / "figure_6_reference_validity_summary.csv")
        frozen = {(row["setup"], row["method"]): row for row in lifecycle}
        self.assertEqual(int(frozen[("A", "frozen")]["false_positive_blocks"]), 4)
        self.assertEqual(int(frozen[("B", "frozen")]["false_positive_blocks"]), 9)
        self.assertEqual(
            [
                round(100.0 * float(frozen[(setup, method)]["fpr"]), 2)
                for setup in ("A", "B")
                for method in ("frozen", "threshold_only", "full_feature_rank")
            ],
            [0.77, 1.15, 1.15, 1.73, 1.15, 1.15],
        )
        self.assertAlmostEqual(float(frozen[("A", "full_feature_rank")]["rank_jaccard"]), 0.7647058823529411)
        self.assertAlmostEqual(float(frozen[("B", "full_feature_rank")]["rank_jaccard"]), 2.0 / 3.0)

        protocol = read_rows(BUNDLE_ROOT / "core" / "section_vh_lifecycle_protocol.csv")
        self.assertEqual(len(protocol), 1)
        self.assertEqual(
            {
                "selected_features": int(protocol[0]["selected_features"]),
                "block_length": int(protocol[0]["block_length"]),
                "aggregation": protocol[0]["aggregation"],
                "weighting": protocol[0]["weighting"],
                "score_mixture": float(protocol[0]["score_mixture"]),
                "threshold_quantile": float(protocol[0]["threshold_quantile"]),
                "initial_reference_fraction": float(
                    protocol[0]["initial_reference_fraction"]
                ),
                "remaining_fraction": float(protocol[0]["remaining_fraction"]),
                "rank_alignment_weight": float(
                    protocol[0]["rank_alignment_weight"]
                ),
                "uses_anomaly_alignment": protocol[0]["uses_anomaly_alignment"],
                "remaining_benign_blocks_per_setup": int(
                    protocol[0]["remaining_benign_blocks_per_setup"]
                ),
            },
            {
                "selected_features": 15,
                "block_length": 100,
                "aggregation": "max",
                "weighting": "uniform",
                "score_mixture": 0.5,
                "threshold_quantile": 0.99,
                "initial_reference_fraction": 0.6,
                "remaining_fraction": 0.4,
                "rank_alignment_weight": 0.0,
                "uses_anomaly_alignment": "False",
                "remaining_benign_blocks_per_setup": 520,
            },
        )

    def test_apple_projection_matches_section_vj(self) -> None:
        envelope = read_rows(BUNDLE_ROOT / "apple" / "figure_8_portability_envelope.csv")
        self.assertEqual(
            [row["stress_condition"] for row in envelope],
            ["CACHE", "ATOMIC", "MEMBW", "BRANCH", "TLB"],
        )
        self.assertEqual(
            [round(float(row["mcc"]), 3) for row in envelope],
            [0.917, 0.878, 0.754, 0.370, 0.367],
        )
        display_view = lambda value: (  # noqa: E731 - compact manuscript mapping
            value.replace("TIER1_ALT", "TIER1")
            .replace("_FULL", "-FULL")
            .replace("_CORE", "-CORE")
        )
        self.assertEqual(
            [
                (
                    display_view(row["observability_view"]),
                    int(row["block_length"]),
                    int(row["selected_features"]),
                    f"{float(row['threshold_quantile']):.3f}",
                )
                for row in envelope
            ],
            [
                ("TIER2-FULL", 250, 8, "0.900"),
                ("TIER2-FULL", 250, 3, "0.950"),
                ("TIER2-FULL", 150, 3, "0.990"),
                ("TIER1-FULL", 100, 10, "0.990"),
                ("TIER1-FULL", 100, 10, "0.990"),
            ],
        )

        averages = read_rows(BUNDLE_ROOT / "apple" / "section_vj_workload_averages.csv")
        values = {
            (row["observability_view"], row["stress_condition"]): round(float(row["mean_mcc"]), 3)
            for row in averages
        }
        self.assertEqual(values[("TIER2_FULL", "CACHE")], 0.994)
        self.assertEqual(values[("TIER2_CORE", "CACHE")], 0.985)
        self.assertEqual(values[("TIER2_FULL", "ATOMIC")], 0.921)
        self.assertEqual(values[("TIER2_FULL", "MEMBW")], 0.750)

        scope = read_rows(BUNDLE_ROOT / "apple" / "section_vj_study_scope.csv")
        self.assertEqual(len(scope), 5)
        self.assertEqual(
            sorted(int(row["available_features"]) for row in scope),
            [7, 8, 11, 18, 45],
        )
        self.assertTrue(all(int(row["evaluated_workloads"]) == 4 for row in scope))
        self.assertTrue(
            all(int(row["evaluated_stress_conditions"]) == 5 for row in scope)
        )

    def test_manifests_do_not_overstate_historical_provenance(self) -> None:
        for profile in ("core", "apple"):
            manifest = json.loads(
                (BUNDLE_ROOT / profile / "evidence_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["evidence_class"], "historical_non_archival_reference")
            self.assertEqual(manifest["archival_status"], "REFERENCE_ONLY")
            self.assertTrue(manifest["source_files"])
            for source in manifest["source_files"]:
                self.assertFalse(Path(source["path"]).is_absolute())
                self.assertRegex(source["sha256"], re.compile(r"^[0-9a-f]{64}$"))
            for source_run in manifest["source_run_manifests"]:
                self.assertTrue(source_run["git_dirty_at_start"])
                self.assertFalse(Path(source_run["path"]).is_absolute())

    def test_rolling_projection_uses_the_paper_window(self) -> None:
        self.assertEqual(
            self.builder.rolling_mean([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], window=25, minimum=6),
            ["", "", "", "", "", 3.5],
        )


if __name__ == "__main__":
    unittest.main()
