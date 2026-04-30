# X-Amplicon Linux Package Manifest

Target platform: Ubuntu 22.04 x86_64.

Included:

- X-Amplicon Python workflow code.
- X-Amplicon Web UI backend and prebuilt frontend.
- Small RDP 16S database: `database/rdp_16s_v18.fa`.
- Linux setup and launcher scripts.
- Linux parameter template: `pipeline_params.linux.yaml`.
- Server test prompt: `LINUX_SERVER_TEST_PROMPT.md`.

Required before testing:

- `bin/usearch`
- `bin/vsearch`

Not included:

- User FASTQ data.
- `metadata.txt`.
- Analysis outputs.
- API keys or `.env`.
- Large SILVA databases.
- Python virtual environment.
- `node_modules`.
