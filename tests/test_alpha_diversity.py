"""Tests for alpha diversity utilities."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.core.alpha_diversity import (
    calculate_alpha_diversity,
    calculate_rarefaction_curve,
    calculate_richness_rarefaction_curve,
    rarefy_otutab,
)

try:
    from skbio.diversity.alpha import ace, chao1, shannon, simpson, sobs

    SKBIO_AVAILABLE = True
except ModuleNotFoundError:
    SKBIO_AVAILABLE = False


@unittest.skipUnless(SKBIO_AVAILABLE, "scikit-bio is not installed")
class AlphaDiversityTests(unittest.TestCase):
    """Alpha diversity test cases."""

    def test_calculate_alpha_diversity(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 1, 2],
                "S2": [0, 3, 1],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )

        result = calculate_alpha_diversity(otutab)

        self.assertEqual(
            list(result.columns),
            ["Observed_OTUs", "Shannon", "Simpson", "Chao1", "ACE"],
        )
        self.assertEqual(result.index.name, "SampleID")

        sample_1 = np.array([1, 1, 2], dtype=np.int64)
        sample_2 = np.array([0, 3, 1], dtype=np.int64)

        self.assertAlmostEqual(result.loc["S1", "Observed_OTUs"], float(sobs(sample_1)))
        self.assertAlmostEqual(result.loc["S1", "Shannon"], float(shannon(sample_1)))
        self.assertAlmostEqual(result.loc["S1", "Simpson"], float(simpson(sample_1)))
        self.assertAlmostEqual(result.loc["S1", "Chao1"], float(chao1(sample_1)))
        self.assertAlmostEqual(result.loc["S1", "ACE"], float(ace(sample_1)))

        self.assertAlmostEqual(result.loc["S2", "Observed_OTUs"], float(sobs(sample_2)))
        self.assertAlmostEqual(result.loc["S2", "Shannon"], float(shannon(sample_2)))
        self.assertAlmostEqual(result.loc["S2", "Simpson"], float(simpson(sample_2)))
        self.assertAlmostEqual(result.loc["S2", "Chao1"], float(chao1(sample_2)))
        self.assertAlmostEqual(result.loc["S2", "ACE"], float(ace(sample_2)))

    def test_calculate_rarefaction_curve_fills_empty_rows_with_zero(self) -> None:
        np.random.seed(0)
        otutab = pd.DataFrame(
            {
                "S1": [2, 1, 0],
                "S2": [0, 0, 0],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )

        result = calculate_rarefaction_curve(otutab, [1, 3, 4])
        metric_columns = ["Observed_OTUs", "Shannon", "Simpson", "Chao1", "ACE"]

        self.assertEqual(len(result), 6)
        self.assertFalse(result[metric_columns].isna().to_numpy().any())

        empty_rows = result.loc[result["SampleID"] == "S2", metric_columns]
        self.assertTrue((empty_rows == 0.0).to_numpy().all())

        over_depth_row = result.loc[
            (result["SampleID"] == "S1") & (result["Depth"] == 4),
            metric_columns,
        ]
        self.assertTrue((over_depth_row == 0.0).to_numpy().all())

    def test_calculate_rarefaction_curve_returns_full_depth_metrics(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [2, 1, 0],
                "S2": [0, 3, 1],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )

        alpha_result = calculate_alpha_diversity(otutab)
        rarefaction_result = calculate_rarefaction_curve(otutab, [3, 4])
        metric_columns = ["Observed_OTUs", "Shannon", "Simpson", "Chao1", "ACE"]

        sample_1_full_depth = rarefaction_result.loc[
            (rarefaction_result["SampleID"] == "S1") & (rarefaction_result["Depth"] == 3),
            metric_columns,
        ].iloc[0]
        sample_2_full_depth = rarefaction_result.loc[
            (rarefaction_result["SampleID"] == "S2") & (rarefaction_result["Depth"] == 4),
            metric_columns,
        ].iloc[0]

        self.assertTrue(
            np.allclose(sample_1_full_depth.to_numpy(), alpha_result.loc["S1", metric_columns].to_numpy())
        )
        self.assertTrue(
            np.allclose(sample_2_full_depth.to_numpy(), alpha_result.loc["S2", metric_columns].to_numpy())
        )

    def test_rarefy_otutab_uses_minimum_depth_and_preserves_totals(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [3, 2, 1],
                "S2": [2, 2, 0],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )

        rarefied, resolved_depth, discarded_samples = rarefy_otutab(otutab, depth=0, seed=1)

        self.assertEqual(resolved_depth, 4)
        self.assertEqual(discarded_samples, [])
        self.assertEqual(list(rarefied.columns), ["S1", "S2"])
        self.assertEqual(rarefied.index.name, "#OTUID")
        self.assertTrue((rarefied.sum(axis=0) == 4).all())

    def test_calculate_richness_rarefaction_curve_returns_wide_table(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [2, 1, 0],
                "S2": [0, 3, 1],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )

        result = calculate_richness_rarefaction_curve(otutab, percentages=[1, 50, 100], seed=1)

        self.assertEqual(result.index.name, "richness")
        self.assertEqual(list(result.index), [1, 50, 100])
        self.assertEqual(list(result.columns), ["S1", "S2"])
        self.assertTrue((result >= 0.0).to_numpy().all())
        self.assertAlmostEqual(result.loc[100, "S1"], 2.0)
        self.assertAlmostEqual(result.loc[100, "S2"], 2.0)


if __name__ == "__main__":
    unittest.main()
