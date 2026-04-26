"""Tests for beta diversity utilities."""

from __future__ import annotations

import unittest
from io import StringIO

import numpy as np
import pandas as pd
import pandas.testing as pdt
from skbio import TreeNode
from skbio.diversity import beta_diversity as skbio_beta_diversity

from src.core.beta_diversity import calculate_beta_distance


class BetaDiversityTests(unittest.TestCase):
    """Beta diversity test cases."""

    def test_calculate_beta_distance_matches_non_phylogenetic_metrics(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 0, 2],
                "S2": [0, 1, 1],
                "S3": [3, 1, 0],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )

        for metric in ["braycurtis", "jaccard", "euclidean", "cityblock", "manhattan"]:
            with self.subTest(metric=metric):
                resolved_metric = "cityblock" if metric == "manhattan" else metric
                data = otutab.T.to_numpy(dtype=np.float64, copy=False)
                if resolved_metric == "jaccard":
                    data = (data > 0).astype(np.int64)

                expected = skbio_beta_diversity(
                    resolved_metric,
                    data,
                    ids=["S1", "S2", "S3"],
                )
                result = calculate_beta_distance(otutab, metric)

                expected_frame = pd.DataFrame(
                    expected.data,
                    index=["S1", "S2", "S3"],
                    columns=["S1", "S2", "S3"],
                )
                expected_frame.index.name = "SampleID"
                expected_frame.columns.name = "SampleID"
                pdt.assert_frame_equal(result, expected_frame)

    def test_calculate_beta_distance_matches_unifrac_metrics(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 0, 2],
                "S2": [0, 1, 1],
                "S3": [3, 1, 0],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )
        tree = TreeNode.read(StringIO("((OTU1:1,OTU2:1):1,OTU3:1)root;"))

        for metric in ["unweighted_unifrac", "weighted_unifrac"]:
            with self.subTest(metric=metric):
                expected = skbio_beta_diversity(
                    metric,
                    otutab.T.to_numpy(dtype=np.float64, copy=False),
                    ids=["S1", "S2", "S3"],
                    taxa=["OTU1", "OTU2", "OTU3"],
                    tree=tree.shear(["OTU1", "OTU2", "OTU3"]),
                )
                result = calculate_beta_distance(otutab, metric, tree=tree)

                expected_frame = pd.DataFrame(
                    expected.data,
                    index=["S1", "S2", "S3"],
                    columns=["S1", "S2", "S3"],
                )
                expected_frame.index.name = "SampleID"
                expected_frame.columns.name = "SampleID"
                pdt.assert_frame_equal(result, expected_frame)

    def test_calculate_beta_distance_requires_tree_for_unifrac(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 0],
                "S2": [0, 1],
            },
            index=["OTU1", "OTU2"],
        )

        with self.assertRaisesRegex(ValueError, "tree is required"):
            calculate_beta_distance(otutab, "weighted_unifrac")

    def test_calculate_beta_distance_rejects_missing_tree_tips(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 0],
                "S2": [0, 1],
            },
            index=["OTU1", "OTU2"],
        )
        tree = TreeNode.read(StringIO("(OTU1:1)root;"))

        with self.assertRaisesRegex(ValueError, "tree is missing OTU IDs"):
            calculate_beta_distance(otutab, "unweighted_unifrac", tree=tree)

    def test_calculate_beta_distance_accepts_normalized_tree_tip_names(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 0, 2],
                "S2": [0, 1, 1],
            },
            index=["OTU_1", "OTU_2", "OTU_3"],
        )
        tree = TreeNode.read(StringIO("(('OTU 1':1,'OTU 2':1):1,'OTU 3':1)root;"))

        result = calculate_beta_distance(otutab, "weighted_unifrac", tree=tree)
        self.assertEqual(result.shape, (2, 2))
        self.assertEqual(list(result.index), ["S1", "S2"])


if __name__ == "__main__":
    unittest.main()
