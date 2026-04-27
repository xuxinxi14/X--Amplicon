"""CLI-only workflow guide for deterministic X-Amplicon runs."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_PARAMS_PATH = "pipeline_params.yaml"
DEFAULT_OUTPUT_ROOT = "work"


def _compact_command(command: str) -> str:
    return " ".join(command.split())


def build_cli_only_workflow(
    *,
    params_path: str = DEFAULT_PARAMS_PATH,
    output_root: str = DEFAULT_OUTPUT_ROOT,
    final_dir: str | None = None,
    include_optional: bool = True,
) -> dict[str, Any]:
    """Build the recommended no-LLM command sequence."""

    resolved_final_dir = final_dir or os.path.join(output_root, "06_final")
    commands: list[dict[str, str]] = [
        {
            "stage": "database",
            "description": "List configured reference databases.",
            "command": "python process.py list-databases",
        },
        {
            "stage": "database",
            "description": "Check the default RDP database without hashing the large FASTA.",
            "command": "python process.py check-database rdp_16s_v18 --no-hash",
        },
        {
            "stage": "preflight",
            "description": "Validate parameters, sample matching, databases, dependencies, and executables.",
            "command": f"python process.py check-pipeline-config --params {params_path}",
        },
        {
            "stage": "analysis",
            "description": "Run the full deterministic 16S pipeline from YAML parameters.",
            "command": f"python process.py run-pipeline-config --params {params_path}",
        },
        {
            "stage": "provenance",
            "description": "Regenerate provenance from the run summary when needed.",
            "command": (
                "python process.py write-provenance "
                f"--summary {os.path.join(resolved_final_dir, 'run_summary.json')}"
            ),
        },
    ]

    if include_optional:
        commands.extend(
            [
                {
                    "stage": "visualization",
                    "description": "Generate standard publication-ready visualizations.",
                    "command": (
                        "python process.py visualization-suite "
                        f"--final-dir {resolved_final_dir} --format html"
                    ),
                },
                {
                    "stage": "statistics",
                    "description": "Generate a comparison plan or run explicit pairwise differential abundance.",
                    "command": (
                        "python process.py differential-abundance "
                        f"--otutab {os.path.join(resolved_final_dir, 'otutab.txt')} "
                        f"--metadata {os.path.join(output_root, '00_input', 'metadata.txt')} "
                        f"--taxonomy {os.path.join(resolved_final_dir, 'taxonomy.tsv')}"
                    ),
                },
                {
                    "stage": "report",
                    "description": "Generate Markdown, HTML, and JSON reports.",
                    "command": f"python process.py generate-report --final-dir {resolved_final_dir}",
                },
            ]
        )

    return {
        "requires_llm": False,
        "params_path": params_path,
        "output_root": output_root,
        "final_dir": resolved_final_dir,
        "commands": commands,
    }


def format_cli_only_workflow(workflow: dict[str, Any]) -> str:
    """Format a CLI-only workflow as terminal-friendly text."""

    commands = workflow.get("commands", [])
    lines = [
        "X-Amplicon CLI-only workflow",
        "",
        "This workflow does not require an LLM API key. It uses process.py and the same",
        "core Python functions that the Agent calls.",
        "",
        f"Params file : {workflow.get('params_path')}",
        f"Output root : {workflow.get('output_root')}",
        f"Final dir   : {workflow.get('final_dir')}",
        "",
        "Recommended commands:",
    ]

    for index, record in enumerate(commands, start=1):
        if not isinstance(record, dict):
            continue
        stage = str(record.get("stage", "step"))
        description = str(record.get("description", ""))
        command = _compact_command(str(record.get("command", "")))
        lines.extend(
            [
                "",
                f"{index}. {stage}",
                f"   {description}",
                f"   {command}",
            ]
        )

    lines.extend(
        [
            "",
            "Notes:",
            "- Use check-pipeline-config before long runs.",
            "- visualization-suite, differential-abundance, and generate-report can be run after the full pipeline finishes.",
            "- agent_cli.py is optional; it only provides a natural-language orchestration layer.",
        ]
    )
    return "\n".join(lines)
