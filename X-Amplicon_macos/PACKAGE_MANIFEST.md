# X-Amplicon macOS Package Manifest

Target platform: macOS.

Included:

- X-Amplicon Python workflow code.
- X-Amplicon Web UI backend and prebuilt frontend.
- Small RDP 16S database: `database/rdp_16s_v18.fa`.
- macOS USEARCH/VSEARCH binaries:
  - `bin/usearch`
  - `bin/vsearch`
- macOS setup and launcher scripts.
- macOS parameter template: `pipeline_params.macos.yaml`.
- macOS test prompt: `MACOS_TEST_PROMPT.md`.

Not included:

- User FASTQ data.
- `metadata.txt`.
- Analysis outputs.
- API keys or `.env`.
- Large SILVA databases.
- Python virtual environment.
- `node_modules`.
