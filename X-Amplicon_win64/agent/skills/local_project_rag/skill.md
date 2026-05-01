# Local Project RAG Skill

This skill lets the agent inspect local project documentation, parameters,
run summaries, and generated output artifacts through bounded, read-only
tools. It is intentionally lightweight and does not require LlamaIndex for
basic operation.

Use this skill when the user asks about project files, completed outputs,
pipeline status, generated plots, or why a previous run failed.

Rules:
- Read only files under the project root unless an explicit root is provided.
- Prefer `read_analysis_summary` for completed pipeline runs.
- Prefer `find_output_artifacts` when the user asks what files were generated.
- Do not infer biological conclusions from file names alone.
