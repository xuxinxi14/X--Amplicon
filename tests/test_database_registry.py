"""Tests for the X-Amplicon database registry module."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

import yaml

from src.core.database_registry import (
    check_database,
    list_databases,
    register_database,
    resolve_database_record,
)


class DatabaseRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_path = Path("tests") / f"tmp_database_registry_{uuid4().hex}"
        self.temp_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        rmtree(self.temp_path, ignore_errors=True)

    def test_builtin_alias_resolves_without_registry_file(self) -> None:
        record = resolve_database_record(
            "rdp",
            registry_path=str(self.temp_path / "missing.yaml"),
            require_exists=False,
        )

        self.assertEqual(record["name"], "rdp_16s_v18")
        self.assertEqual(record["taxonomy_format"], "sintax")
        self.assertTrue(str(record["path"]).endswith(str(Path("database") / "rdp_16s_v18.fa")))

    def test_register_and_resolve_database(self) -> None:
        fasta_path = self.temp_path / "custom.fa"
        fasta_bytes = b">OTU1\nACGT\n"
        fasta_path.write_bytes(fasta_bytes)
        registry_path = self.temp_path / "databases.yaml"

        registered = register_database(
            name="custom_16s",
            sequence_path=str(fasta_path),
            version="v1",
            taxonomy_format="sintax",
            database_type="taxonomy_annotation",
            registry_path=str(registry_path),
            aliases=["custom"],
        )

        self.assertEqual(registered["status"], "passed")
        self.assertEqual(registered["sha256"], hashlib.sha256(fasta_bytes).hexdigest())
        registry_data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
        self.assertEqual(
            registry_data["databases"]["custom_16s"]["sequence_path"],
            "custom.fa",
        )

        resolved = resolve_database_record(
            "custom",
            registry_path=str(registry_path),
            include_hash=True,
        )
        self.assertEqual(resolved["name"], "custom_16s")
        self.assertTrue(resolved["hash_matches"])

    def test_check_database_accepts_direct_fasta_path(self) -> None:
        fasta_path = self.temp_path / "direct.fa"
        fasta_path.write_text(">OTU1\nACGT\n", encoding="utf-8")

        record = check_database(str(fasta_path), include_hash=True)

        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["source"], "path")
        self.assertIn("sha256", record)

    def test_list_databases_includes_registered_records(self) -> None:
        fasta_path = self.temp_path / "custom.fa"
        fasta_path.write_text(">OTU1\nACGT\n", encoding="utf-8")
        registry_path = self.temp_path / "databases.yaml"
        register_database(
            name="custom_16s",
            sequence_path=str(fasta_path),
            registry_path=str(registry_path),
        )

        names = {
            record["name"]
            for record in list_databases(registry_path=str(registry_path), include_builtin=False)
        }

        self.assertEqual(names, {"custom_16s"})

    def test_agent_tool_discovery_includes_database_tools(self) -> None:
        from agent.tools import get_tool_map

        tool_map = get_tool_map()
        self.assertIn("list_registered_databases", tool_map)
        self.assertIn("check_registered_database", tool_map)
        self.assertIn("register_database", tool_map)


if __name__ == "__main__":
    unittest.main()
