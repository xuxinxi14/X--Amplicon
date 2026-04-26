"""Tests for OTU table rarefaction edge cases."""

from __future__ import annotations

import random
import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from src.core.otutab_rare import _rarefy_counts, run_otutab_rare


class OtuTabRareTests(unittest.TestCase):
    """Verify rarefaction validates invalid depth values cleanly."""

    def test_rarefy_counts_rejects_non_positive_depth(self) -> None:
        with self.assertRaisesRegex(ValueError, "depth must be greater than 0"):
            _rarefy_counts([1, 2, 3], 0, random.Random(1))

    def test_run_otutab_rare_rejects_zero_auto_depth(self) -> None:
        temp_path = Path("tests") / f"tmp_rare_{uuid4().hex}"
        temp_path.mkdir(parents=True, exist_ok=True)
        try:
            input_path = temp_path / "otutab.txt"
            input_path.write_text(
                "#OTUID\tS1\tS2\n"
                "OTU1\t0\t5\n"
                "OTU2\t0\t3\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "depth resolves to 0"):
                run_otutab_rare(str(input_path), depth=0)
        finally:
            rmtree(temp_path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
