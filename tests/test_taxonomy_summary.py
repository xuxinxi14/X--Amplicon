"""Tests for taxonomy parsing and summarization utilities."""

from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pandas.testing as pdt

from src.core.taxonomy_summary import (
    parse_sintax_to_dataframe,
    summarize_taxa_abundance,
)


class TaxonomySummaryTests(unittest.TestCase):
    """Taxonomy summary test cases."""

    def test_parse_sintax_to_dataframe_standardizes_missing_ranks(self) -> None:
        sintax_content = "\n".join(
            [
                (
                    "OTU1\t"
                    "d:Bacteria(1.0),p:Firmicutes(0.9),c:Bacilli(0.8),"
                    "o:Lactobacillales(0.7),f:Lactobacillaceae(0.6),"
                    "g:Lactobacillus(0.5),s:Lactobacillus_acidophilus(0.4)\t+\t"
                    "d:Bacteria,p:Firmicutes,c:Bacilli,o:Lactobacillales,"
                    "f:Lactobacillaceae,g:Lactobacillus,s:Lactobacillus_acidophilus"
                ),
                "OTU2\tk:Bacteria(1.0),p:Proteobacteria(0.9),g:Escherichia(0.8)",
                "OTU3\t\t+\t",
            ]
        )

        sintax_path = Path("tests") / f"tmp_{uuid4().hex}.sintax"
        try:
            sintax_path.write_text(sintax_content, encoding="utf-8")
            result = parse_sintax_to_dataframe(str(sintax_path))
        finally:
            sintax_path.unlink(missing_ok=True)

        expected = pd.DataFrame(
            [
                {
                    "OTUID": "OTU1",
                    "Kingdom": "Bacteria",
                    "Phylum": "Firmicutes",
                    "Class": "Bacilli",
                    "Order": "Lactobacillales",
                    "Family": "Lactobacillaceae",
                    "Genus": "Lactobacillus",
                    "Species": "Lactobacillus_acidophilus",
                },
                {
                    "OTUID": "OTU2",
                    "Kingdom": "Bacteria",
                    "Phylum": "Proteobacteria",
                    "Class": "Unassigned",
                    "Order": "Unassigned",
                    "Family": "Unassigned",
                    "Genus": "Escherichia",
                    "Species": "Unassigned",
                },
                {
                    "OTUID": "OTU3",
                    "Kingdom": "Unassigned",
                    "Phylum": "Unassigned",
                    "Class": "Unassigned",
                    "Order": "Unassigned",
                    "Family": "Unassigned",
                    "Genus": "Unassigned",
                    "Species": "Unassigned",
                },
            ]
        )
        pdt.assert_frame_equal(result, expected)

    def test_summarize_taxa_abundance_sums_requested_rank(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [10, 3, 7],
                "S2": [5, 4, 8],
            },
            index=["OTU1", "OTU2", "OTU3"],
        )
        taxonomy = pd.DataFrame(
            [
                {
                    "OTUID": "OTU1",
                    "Kingdom": "Bacteria",
                    "Phylum": "Firmicutes",
                    "Class": "Bacilli",
                    "Order": "Lactobacillales",
                    "Family": "Lactobacillaceae",
                    "Genus": "Lactobacillus",
                    "Species": "s1",
                },
                {
                    "OTUID": "OTU2",
                    "Kingdom": "Bacteria",
                    "Phylum": "Firmicutes",
                    "Class": "Bacilli",
                    "Order": "Lactobacillales",
                    "Family": "Lactobacillaceae",
                    "Genus": "Lactobacillus",
                    "Species": "s2",
                },
                {
                    "OTUID": "OTU3",
                    "Kingdom": "Bacteria",
                    "Phylum": "Proteobacteria",
                    "Class": "Gammaproteobacteria",
                    "Order": "Enterobacterales",
                    "Family": "Enterobacteriaceae",
                    "Genus": "Escherichia",
                    "Species": "s3",
                },
            ]
        )

        result = summarize_taxa_abundance(otutab, taxonomy, "Genus")

        expected = pd.DataFrame(
            {
                "S1": [65.0, 35.0],
                "S2": [52.94117647058824, 47.05882352941176],
                "All": [66.66666666666666, 33.33333333333333],
            },
            index=["Lactobacillus", "Escherichia"],
        )
        expected.index.name = "Genus"
        pdt.assert_frame_equal(result, expected)

    def test_summarize_taxa_abundance_rejects_missing_taxonomy_ids(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [1, 2],
                "S2": [3, 4],
            },
            index=["OTU1", "OTU2"],
        )
        taxonomy = pd.DataFrame(
            [
                {
                    "OTUID": "OTU1",
                    "Kingdom": "Bacteria",
                    "Phylum": "Firmicutes",
                    "Class": "Bacilli",
                    "Order": "Lactobacillales",
                    "Family": "Lactobacillaceae",
                    "Genus": "Lactobacillus",
                    "Species": "s1",
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "taxonomy is missing OTU IDs"):
            summarize_taxa_abundance(otutab, taxonomy, "Phylum")

    def test_summarize_taxa_abundance_keeps_zero_abundance_taxa_from_taxonomy(self) -> None:
        otutab = pd.DataFrame(
            {
                "S1": [10, 3],
                "S2": [5, 4],
            },
            index=["OTU1", "OTU2"],
        )
        taxonomy = pd.DataFrame(
            [
                {
                    "OTUID": "OTU1",
                    "Kingdom": "Bacteria",
                    "Phylum": "Firmicutes",
                    "Class": "Bacilli",
                    "Order": "Lactobacillales",
                    "Family": "Lactobacillaceae",
                    "Genus": "Lactobacillus",
                    "Species": "s1",
                },
                {
                    "OTUID": "OTU2",
                    "Kingdom": "Bacteria",
                    "Phylum": "Proteobacteria",
                    "Class": "Gammaproteobacteria",
                    "Order": "Enterobacterales",
                    "Family": "Enterobacteriaceae",
                    "Genus": "Escherichia",
                    "Species": "s2",
                },
                {
                    "OTUID": "OTU3",
                    "Kingdom": "Bacteria",
                    "Phylum": "Unassigned",
                    "Class": "Unassigned",
                    "Order": "Unassigned",
                    "Family": "Unassigned",
                    "Genus": "Unassigned",
                    "Species": "Unassigned",
                },
            ]
        )

        result = summarize_taxa_abundance(otutab, taxonomy, "Genus")

        self.assertIn("(Unassigned)", result.index)
        self.assertTrue((result.loc["(Unassigned)", ["S1", "S2"]] == 0.0).all())
        self.assertAlmostEqual(result.loc["(Unassigned)", "All"], 100.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
