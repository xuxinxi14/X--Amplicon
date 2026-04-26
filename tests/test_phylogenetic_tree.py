"""Tests for pure-Python phylogenetic tree generation."""

from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import pandas as pd
from skbio import TreeNode

from src.core.beta_diversity import calculate_beta_distance
from src.core.phylogenetic_tree import run_phylogenetic_tree_generation


class PhylogeneticTreeGenerationTests(unittest.TestCase):
    """Verify generated Newick trees can be consumed by UniFrac."""

    def test_run_phylogenetic_tree_generation_writes_unifrac_compatible_tree(self) -> None:
        temp_path = Path("tests") / f"tmp_tree_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            fasta_path = temp_path / "otus.fa"
            tree_path = temp_path / "otus.tree"
            fasta_path.write_text(
                ">OTU1\nACGT\n>OTU2\nACGA\n>OTU3\nTCGA\n",
                encoding="utf-8",
            )

            outputs = run_phylogenetic_tree_generation(
                input_fasta=str(fasta_path),
                output_tree_path=str(tree_path),
            )

            self.assertEqual(outputs["record_count"], 3)
            self.assertEqual(outputs["linkage"], "max")
            self.assertTrue(tree_path.is_file())

            tree = TreeNode.read(StringIO(tree_path.read_text(encoding="utf-8")))
            self.assertEqual({tip.name for tip in tree.tips()}, {"OTU1", "OTU2", "OTU3"})

            otutab = pd.DataFrame(
                {
                    "S1": [5, 0, 2],
                    "S2": [0, 4, 1],
                },
                index=["OTU1", "OTU2", "OTU3"],
            )
            result = calculate_beta_distance(otutab, "weighted_unifrac", tree=tree)
            self.assertEqual(result.shape, (2, 2))
        finally:
            rmtree(temp_path, ignore_errors=True)

    def test_run_phylogenetic_tree_generation_handles_single_record(self) -> None:
        temp_path = Path("tests") / f"tmp_tree_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            fasta_path = temp_path / "otus.fa"
            tree_path = temp_path / "otus.tree"
            fasta_path.write_text(">OTU1\nACGT\n", encoding="utf-8")

            run_phylogenetic_tree_generation(
                input_fasta=str(fasta_path),
                output_tree_path=str(tree_path),
            )
            tree = TreeNode.read(StringIO(tree_path.read_text(encoding="utf-8")))
            otutab = pd.DataFrame({"S1": [5]}, index=["OTU1"])
            result = calculate_beta_distance(otutab, "unweighted_unifrac", tree=tree)

            self.assertEqual(result.shape, (1, 1))
            self.assertEqual(result.iloc[0, 0], 0.0)
        finally:
            rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
