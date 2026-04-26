"""Tests for group abundance filtering utilities."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd
import pandas.testing as pdt

from src.core.feature_filter import calculate_group_abundance


class FeatureFilterTests(unittest.TestCase):
    """Feature filter test cases."""

    def test_calculate_group_abundance_filters_rows(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [10, 0, 1],
                "S2": [10, 0, 1],
                "S3": [0, 9, 1],
                "S4": [0, 9, 1],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )
        metadata = pd.DataFrame(
            {
                "SampleID": ["S1", "S2", "S3", "S4"],
                "Group": ["A", "A", "B", "B"],
            }
        )

        result = calculate_group_abundance(
            otutab=otutab,
            metadata=metadata,
            group_col="Group",
            threshold=0.25,
        )

        expected = pd.DataFrame(
            {
                "A": [1000.0 / 11.0, 0.0],
                "B": [0.0, 90.0],
            },
            index=["OTU1", "OTU2"],
        )
        expected.index.name = "OTUID"
        expected.columns.name = "Group"

        pdt.assert_index_equal(result.index, expected.index)
        pdt.assert_index_equal(result.columns, expected.columns)
        self.assertTrue(np.allclose(result.to_numpy(), expected.to_numpy()))

    def test_calculate_group_abundance_rejects_zero_sum_samples(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [0, 0],
                "S2": [1, 1],
            },
            index=["OTU1", "OTU2"],
        )
        metadata = pd.DataFrame({"Group": ["A", "A"]}, index=["S1", "S2"])

        with self.assertRaisesRegex(ValueError, "zero-sum"):
            calculate_group_abundance(
                otutab=otutab,
                metadata=metadata,
                group_col="Group",
            )


if __name__ == "__main__":
    unittest.main()
