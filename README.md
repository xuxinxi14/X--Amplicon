[English](README.md) | [中文](README_zh.md)

# X-Amplicon

X-Amplicon is a Python workflow and AI Agent for 16S rRNA amplicon paired-end sequencing data. Starting from raw paired-end FASTQ files and a metadata table, it performs read merging, quality control, dereplication, OTU/ASV generation, chimera removal, OTU table construction, taxonomic annotation, filtering, rarefaction, alpha/beta diversity analysis, taxonomy summary, visualization, and pairwise differential abundance analysis.

The recommended deterministic entry point is `process.py run-pipeline-config`, with parameters managed by `pipeline_params.yaml`. Agent mode is optional: `agent_cli.py` calls the same core tools through a natural-language layer, but the complete analysis, visualization, statistics, provenance, database checks, and report generation can all be run without an LLM API key.

## At a Glance

| Item | Status |
| --- | --- |
| Primary platform | Windows-first; Python CLI can be adapted to other systems |
| Main deterministic entry point | `python process.py run-pipeline-config --params pipeline_params.yaml` |
| LLM requirement | Not required for the core workflow; only needed for natural-language Agent orchestration |
| Input data | Paired-end FASTQ files plus a sample metadata table |
| Main outputs | OTU/ASV table, taxonomy table, alpha/beta diversity, visualizations, differential abundance, provenance, report |
| External tools | USEARCH and VSEARCH for the complete raw FASTQ workflow |
| Large files in Git | Not tracked; users provide local FASTQ files, databases, and executables |

Choose the workflow that matches your situation:

| User goal | Recommended route |
| --- | --- |
| Run a reproducible analysis from parameters | Edit `pipeline_params.yaml`, then use `process.py run-pipeline-config` |
| Check whether inputs and executables are ready | `process.py check-pipeline-config --params pipeline_params.yaml` |
| Work without any LLM key | `process.py cli-only-workflow` |
| Ask for steps in natural language | `agent_cli.py` with a configured LLM API key |
| Use Agent shell but no LLM | `agent_cli.py --offline` |
| Generate publication-ready outputs after analysis | `visualization-suite`, `differential-abundance`, then `generate-report` |

All command examples assume you are running from the repository root directory:

```powershell
cd X-Amplicon
```

## 1. Quick Start

When using on Windows for the first time, run the initialization script:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

If your network is slow when installing dependencies (common in China), use the Tsinghua PyPI mirror:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror
```

If you need to export `png`, `pdf`, `svg`, or `all` static plots, add `-InstallStaticExport` to install `kaleido`:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallStaticExport
```

If you want to install optional Agent skill dependencies for PubMed search, LlamaIndex, evaluation, and tracing, add `-InstallSkillDeps`:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps
```

Before running real data, make sure these local resources exist:

| Resource | Typical path | Required for |
| --- | --- | --- |
| Metadata table | `metadata.txt` or a user-defined TSV path | Full pipeline and downstream statistics |
| Paired FASTQ directory | `seq\` or a user-defined directory | Full raw FASTQ pipeline |
| USEARCH executable | `bin\windows\usearch.exe` or `usearch_path` | ASV/OTU steps and some table utilities |
| VSEARCH executable | `bin\windows\vsearch.exe` or `vsearch_path` | OTU clustering, chimera checking, SINTAX annotation |
| RDP/SILVA FASTA database | `databas\rdp_16s_v18.fa`, `databas\silva_16s_v123.fa`, or a registered database | Chimera checking and taxonomy annotation |

Minimal end-to-end command sequence:

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
python process.py run-pipeline-config --params pipeline_params.yaml
python process.py visualization-suite --final-dir work\06_final --format html
python process.py differential-abundance --reference-group WT --format html
python process.py generate-report --final-dir work\06_final
```

Replace `WT` with the actual reference/control group in your metadata, or run `differential-abundance` without `--reference-group` to generate a comparison plan first.

### 1.1 Check Configuration

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
```

This command only validates parameters, input paths, sample matching, and external executables — it does not start any time-consuming analysis.

Equivalent pre-check entry point:

```powershell
python process.py run-pipeline-config --params pipeline_params.yaml --check-only
```

`--dry-run` is an alias for `--check-only`.

Database registry preflight:

```powershell
python process.py list-databases
python process.py check-database rdp_16s_v18
```

### 1.2 Run the Full Pipeline

```powershell
python process.py run-pipeline-config --params pipeline_params.yaml
```

### 1.3 Generate Standard Visualizations

Run after the full pipeline completes:

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

Plot output defaults to `work\06_final\plots\`, with each chart type placed in its own subdirectory and an `index.html` page generated for browsing.

### 1.4 Run Differential Abundance

Use an explicit comparison:

```powershell
python process.py differential-abundance `
  --compare KO:WT `
  --format html
```

Or generate all case groups versus a reference group:

```powershell
python process.py differential-abundance `
  --reference-group WT `
  --format html
```

If neither `--compare` nor `--reference-group` is supplied, X-Amplicon writes `comparison_plan.tsv` only and waits for user confirmation.

### 1.5 Use CLI-Only Mode

The full workflow does not require an LLM API key:

```powershell
python process.py cli-only-workflow
```

This prints the recommended command sequence for database checks, parameter validation, full pipeline execution, provenance, visualization, statistics, and report generation.

### 1.6 Launch the Agent

```powershell
python agent_cli.py
```

If no LLM API key is configured, `agent_cli.py` starts in no-LLM mode. Slash commands such as `/params`, `/status`, `/tools`, `/report`, `/config`, and `/language` remain available, while natural-language tool orchestration is disabled until an API key is configured. Use `--require-llm` when you want startup to fail instead of falling back to no-LLM mode.

Common interactive commands:

| Command | Description |
| --- | --- |
| `/tools` | List tools available to the Agent |
| `/params` | View current pipeline parameters |
| `/language` | Switch CLI language; enter `Chinese` or `English` |
| `/status` | View session status |
| `/report` | Generate Markdown and HTML reports under `work\06_final\report` |
| `/config` | View model and API configuration |
| `/quit` | Exit |

Review Agent evaluation logs from the terminal:

```powershell
python process.py agent-evaluation-log
python process.py agent-evaluation-log --export-json run_logs\agent_evaluation_log_export.json
```

## 2. Input Files and Parameters

The full pipeline reads `pipeline_params.yaml` from the repository root by default. Common fields:

| Parameter | Description |
| --- | --- |
| `metadata_path` | Path to the metadata table; first column is sample ID, or a `SampleID` column is present |
| `seq_dir` | Directory containing raw paired-end FASTQ files |
| `read1_suffix` / `read2_suffix` | Suffixes used to match R1/R2 files by sample ID |
| `output_root` | Output root directory; usually `work` |
| `fastq_stripleft` / `fastq_stripright` | Number of bases to trim from each end of reads before filtering |
| `fastq_maxee_rate` | Maximum expected error rate for quality filtering |
| `feature_method` | `usearch-asv`, `usearch-otu`, or `vsearch-otu` |
| `feature_minsize` | Minimum abundance for unique sequences or feature generation |
| `chimera_mode` | `ref` or `none` |
| `reference_db` | Registered database name or reference FASTA for chimera checking |
| `otutab_method` | `usearch` or `vsearch` |
| `annotation_database` | Registered database name, alias, or FASTA path for SINTAX annotation |
| `filter_route` | `16s`, `its`, or `none` |
| `rarefaction_depth` | Rarefaction depth; `0` means auto-select the minimum sample depth |
| `rarefaction_seed` | Random seed for rarefaction and rarefaction curve |
| `threads` | Number of threads for external commands |
| `usearch_path` / `vsearch_path` | Optional; explicitly specify executable paths |

Input conventions:

- Sample IDs in metadata must match FASTQ file names using the `read1_suffix` and `read2_suffix` patterns.
- OTU/ASV tables have feature IDs as rows and sample IDs as columns, with values as read counts.
- The full pipeline automatically generates `otus.tree` from the final `otus.fa`; you do not need to provide a tree file manually for routine runs.
- When running UniFrac beta diversity separately, you can explicitly provide an external tree via `--tree`.

Example minimal input layout:

```text
X-Amplicon/
  pipeline_params.yaml
  metadata.txt
  seq/
    S1_1.fq.gz
    S1_2.fq.gz
    S2_1.fq.gz
    S2_2.fq.gz
  bin/
    windows/
      usearch.exe
      vsearch.exe
  databas/
    rdp_16s_v18.fa
```

Example metadata table:

```text
SampleID	Group
S1	WT
S2	KO
```

For the example above, `pipeline_params.yaml` should use `read1_suffix: _1.fq.gz` and `read2_suffix: _2.fq.gz`.

## 3. What the Full Pipeline Does

`run-pipeline-config` executes the following steps in order:

1. Read sample IDs from metadata.
2. Match raw paired-end FASTQ files.
3. Merge paired-end reads.
4. Trim and quality-filter reads.
5. Dereplicate.
6. Generate OTU or ASV representative sequences.
7. Remove chimeras against reference database, or skip based on configuration.
8. Generate the raw `otutab.txt`.
9. Run VSEARCH SINTAX taxonomic annotation.
10. Filter non-target taxa by `filter_route` to produce the final core results.
11. Generate `otutab_rare.txt`, alpha diversity, alpha rarefaction, beta distance matrices, and taxonomy summary.
12. If plots or pairwise differential abundance statistics are needed, run `visualization-suite` and `differential-abundance` separately or ask the Agent to call the same tools.

`run-pipeline-config` produces only tables and analysis results by default; plots are a separate step after the full pipeline.

## 4. Output Structure

Default output directory structure:

```text
work/
  00_input/
  01_merged/
  02_filtered/
  03_uniques/
  04_features/
  05_raw_results/
  06_final/
    otutab.txt
    otutab_rare.txt
    otutab.id
    otus.fa
    otus.tree
    otus.sintax
    taxonomy.tsv
    run_summary.json
    provenance.json
    provenance.md
    alpha/
      alpha_diversity.tsv
      alpha_rarefaction.tsv
    beta/
      braycurtis.tsv
      jaccard.tsv
      euclidean.tsv
      manhattan.tsv
      unweighted_unifrac.tsv
      weighted_unifrac.tsv
    taxonomy_summary/
      kingdom.tsv
      phylum.tsv
      class.tsv
      order.tsv
      family.tsv
      genus.tsv
      species.tsv
    plots/
      index.html
      alpha_boxplot_chart/
        index.html
      alpha_barplot_chart/
        index.html
      alpha_rare_chart/
        index.html
      beta_pcoa_chart/
        index.html
      beta_cpcoa_chart/
        index.html
      beta_heatmap_chart/
        index.html
      taxonomy_stacked_bar_chart/
        index.html
      taxonomy_heatmap_chart/
        index.html
    report/
      analysis_report.md
      analysis_report.html
      analysis_report_data.json
    statistics/
      differential/
        comparison_plan.tsv
        comparison_result/
          KO_vs_WT/
            differential_results.tsv
            differential_results_significant.tsv
            relative_abundance_percent.tsv
        volcano_chart/
          KO_vs_WT/
            volcano.html
        heatmap_chart/
          KO_vs_WT/
            heatmap.html
            heatmap_matrix_zscore.tsv
```

`run_summary.json` is a machine-readable summary of the full pipeline run. It should be the first file checked by both the Agent and for manual troubleshooting. It records effective parameters, executed steps, key outputs, rarefaction depth, beta metrics, tree file path, provenance paths, and failure information.

`provenance.json` is the reproducibility record for the run. It records the X-Amplicon git commit and dirty state, Python version, key Python package versions, USEARCH/VSEARCH paths and best-effort versions, reference database file metadata and SHA-256 hashes, the effective parameter snapshot, per-step timing/status/file references, and hashes for key final output files. `provenance.md` is a compact human-readable version of the same record.

`beta/` outputs `braycurtis`, `jaccard`, `euclidean`, and `manhattan` by default. `cityblock` is accepted only as a compatibility alias; all documentation and output filenames use `manhattan`.

Agent runtime records are written outside `work/` by default:

```text
run_logs/
  agent_tool_trace.jsonl
  agent_evaluation_log.jsonl
```

`agent_tool_trace.jsonl` is the lower-level tool-call trace. `agent_evaluation_log.jsonl` records tool-call events and user-task events with status, duration, error labels, and recovery-path labels for later Agent evaluation.

## 5. CLI Overview

List all subcommands:

```powershell
python process.py --help
```

View options for a specific subcommand:

```powershell
python process.py beta-diversity --help
```

Each module below is described with: purpose, primary inputs, primary outputs, and terminal usage.

### 5.1 `check-pipeline-config`

Purpose: Validate `pipeline_params.yaml`, input files, sample matching, databases, and USEARCH/VSEARCH executables.

Primary inputs: `pipeline_params.yaml`

Primary outputs: Terminal validation report; no analysis results written.

Terminal usage:

```powershell
python process.py check-pipeline-config `
  --params pipeline_params.yaml
```

### 5.2 `run-pipeline-config`

Purpose: Run the complete 16S analysis pipeline using YAML parameters.

Primary inputs: `pipeline_params.yaml`

Primary outputs: `output_root\06_final\`, `run_summary.json`, `provenance.json`, and `provenance.md`

Terminal usage:

```powershell
python process.py run-pipeline-config `
  --params pipeline_params.yaml
```

Check without running:

```powershell
python process.py run-pipeline-config `
  --params pipeline_params.yaml `
  --check-only
```

Regenerate provenance from an existing completed or failed run summary:

```powershell
python process.py write-provenance `
  --summary work\06_final\run_summary.json
```

### 5.2.1 `cli-only-workflow`

Purpose: Print the deterministic no-LLM workflow for users who want to run X-Amplicon entirely from `process.py`.

Primary inputs: Optional `pipeline_params.yaml` path and output root.

Primary outputs: Terminal command guide; no analysis results written.

Terminal usage:

```powershell
python process.py cli-only-workflow
```

Customize paths:

```powershell
python process.py cli-only-workflow `
  --params pipeline_params.yaml `
  --output-root work
```

### 5.3 `run-pipeline`

Purpose: Run the full pipeline by passing parameters directly on the command line, without a YAML file. Useful for overriding parameters on the fly or scripted runs.

Primary inputs: metadata, FASTQ directory, filter parameters, and pipeline parameters.

Primary outputs: Complete staged output under `--output-root`.

Terminal usage:

```powershell
python process.py run-pipeline `
  --metadata metadata.txt `
  --seq-dir seq `
  --output-root work `
  --fastq-stripleft 0 `
  --fastq-stripright 0 `
  --fastq-maxee-rate 0.01 `
  --feature-method usearch-asv `
  --otutab-method usearch `
  --annotation-database rdp_16s_v18 `
  --filter-route 16s `
  --rarefaction-depth 0 `
  --rarefaction-seed 1 `
  --threads 4
```

### 5.4 `usearch-asv`

Purpose: Generate ASV/ZOTU representative sequences from a dereplicated FASTA using USEARCH UNOISE3.

Primary inputs: Dereplicated FASTA.

Primary outputs: ASV/ZOTU FASTA and associated intermediate files.

Terminal usage:

```powershell
python process.py usearch-asv `
  --input work\03_uniques\uniques.fa `
  --output work\04_features `
  --minsize 10 `
  --threads 4
```

### 5.5 `usearch-otu`

Purpose: Generate 97% OTU representative sequences using USEARCH `cluster_otus`.

Primary inputs: Dereplicated FASTA.

Primary outputs: OTU FASTA.

Terminal usage:

```powershell
python process.py usearch-otu `
  --input work\03_uniques\uniques.fa `
  --output work\04_features `
  --minsize 10 `
  --threads 4
```

### 5.6 `vsearch-otu`

Purpose: Generate OTU representative sequences using VSEARCH clustering.

Primary inputs: Dereplicated FASTA.

Primary outputs: OTU FASTA.

Terminal usage:

```powershell
python process.py vsearch-otu `
  --input work\03_uniques\uniques.fa `
  --output work\04_features `
  --identity 0.97 `
  --minsize 1 `
  --threads 4
```

### 5.7 `vsearch-uchime-ref`

Purpose: Remove chimeras against a reference database using VSEARCH `uchime_ref`; can be skipped with `--chimera-mode none`.

Primary inputs: Feature FASTA and reference database.

Primary outputs: Non-chimeric FASTA.

Terminal usage:

```powershell
python process.py vsearch-uchime-ref `
  --input work\04_features\otus.fa `
  --output work\04_features `
  --reference-db databas\rdp_16s_v18.fa `
  --chimera-mode ref `
  --threads 4
```

### 5.8 `otutab`

Purpose: Map filtered reads against representative sequences to generate an OTU/ASV feature table.

Primary inputs: Filtered reads FASTA, representative sequences FASTA.

Primary outputs: OTU/ASV count table.

Terminal usage:

```powershell
python process.py otutab `
  --input work\02_filtered\filtered.fa `
  --representatives work\04_features\otus.fa `
  --output work\05_raw_results `
  --method usearch `
  --threads 4
```

Using the VSEARCH backend:

```powershell
python process.py otutab `
  --input work\02_filtered\filtered.fa `
  --representatives work\04_features\otus.fa `
  --output work\05_raw_results `
  --method vsearch `
  --identity 0.97 `
  --threads 4
```

### 5.9 `vsearch-sintax`

Purpose: Taxonomically annotate representative sequences using VSEARCH SINTAX.

Primary inputs: OTU/ASV representative FASTA and a registered database name, alias, or FASTA path.

Primary outputs: `otus.sintax`.

Terminal usage:

```powershell
python process.py vsearch-sintax `
  --input work\04_features\otus.fa `
  --output work\05_raw_results `
  --database rdp_16s_v18 `
  --sintax-cutoff 0.1 `
  --threads 4
```

`--database` accepts built-in aliases such as `rdp` and `silva`, names registered in `databases.yaml`, or a direct FASTA path.

### 5.10 `otutab-filter`

Purpose: Filter the feature table and representative sequences by taxonomy route.

Primary inputs: Raw OTU table, SINTAX annotations, representative sequences FASTA.

Primary outputs: Filtered `otutab.txt`, `otus.fa`, `otus.sintax`, feature ID list, and statistics table.

Terminal usage:

```powershell
python process.py otutab-filter `
  --input work\05_raw_results\otutab.txt `
  --taxonomy work\05_raw_results\otus.sintax `
  --representatives work\04_features\otus.fa `
  --output work\06_final `
  --route 16s
```

`--route 16s` retains Bacteria/Archaea and removes Chloroplast/Mitochondria; `--route its` retains Fungi; `--route none` applies no filtering.

### 5.11 `otutab-rare`

Purpose: Rarefy the OTU table and generate an alpha diversity table and USEARCH otutab stats.

Primary inputs: OTU table.

Primary outputs: Rarefied OTU table, alpha diversity table, and stats file.

Terminal usage:

```powershell
python process.py otutab-rare `
  --input work\06_final\otutab.txt `
  --depth 0 `
  --seed 1 `
  --normalize work\06_final\otutab_rare.txt `
  --output work\06_final\alpha\alpha_diversity.tsv `
  --stats-path work\06_final\otutab_stats.txt
```

### 5.12 `alpha-diversity`

Purpose: Calculate alpha diversity from an OTU table; optionally generate a rarefaction curve.

Primary inputs: OTU table.

Primary outputs: Alpha diversity TSV; optional rarefaction TSV.

Terminal usage:

```powershell
python process.py alpha-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\alpha\alpha_diversity.tsv
```

With rarefaction curve:

```powershell
python process.py alpha-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\alpha\alpha_diversity.tsv `
  --rarefaction-output work\06_final\alpha\alpha_rarefaction.tsv `
  --depth 1000 `
  --depth 5000 `
  --depth 10000
```

### 5.13 `beta-diversity`

Purpose: Calculate beta diversity distance matrices from an OTU table.

Primary inputs: OTU table; UniFrac also requires a tree file.

Primary outputs: One or more distance matrix TSV files.

Terminal usage:

```powershell
python process.py beta-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\beta `
  --metric braycurtis `
  --metric jaccard `
  --metric euclidean `
  --metric manhattan
```

Calculate UniFrac:

```powershell
python process.py beta-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\beta `
  --metric unweighted_unifrac `
  --metric weighted_unifrac `
  --tree work\06_final\otus.tree
```

### 5.14 `phylogenetic-tree`

Purpose: Generate a rooted Newick tree from the representative sequence FASTA for use with UniFrac.

Primary inputs: `otus.fa`.

Primary outputs: `otus.tree`.

Terminal usage:

```powershell
python process.py phylogenetic-tree `
  --input work\06_final\otus.fa `
  --output work\06_final\otus.tree `
  --linkage max
```

### 5.15 `taxonomy-summary`

Purpose: Parse SINTAX annotations and summarize relative abundance by taxonomy rank.

Primary inputs: `otus.sintax`; optional `otutab.txt`.

Primary outputs: `taxonomy.tsv` and `taxonomy_summary\*.tsv`.

Terminal usage:

```powershell
python process.py taxonomy-summary `
  --sintax work\06_final\otus.sintax `
  --otutab work\06_final\otutab.txt `
  --output work\06_final
```

Summarize only selected ranks:

```powershell
python process.py taxonomy-summary `
  --sintax work\06_final\otus.sintax `
  --otutab work\06_final\otutab.txt `
  --rank Phylum `
  --rank Genus `
  --output work\06_final
```

### 5.16 `feature-filter`

Purpose: Calculate mean relative abundance of features per metadata group and filter low-abundance features.

Primary inputs: OTU table and metadata.

Primary outputs: Group abundance table.

Terminal usage:

```powershell
python process.py feature-filter `
  --input work\06_final\otutab.txt `
  --metadata metadata.txt `
  --group-col Group `
  --threshold 0.001 `
  --output work\06_final\group_abundance.tsv
```

Note: `feature-filter` is a standalone analysis command and is not executed automatically by `run-pipeline-config`.

### 5.17 `visualization-suite`

Purpose: Batch-generate publication-ready alpha, beta, and taxonomy plots from the `06_final` output of the full pipeline.

Primary inputs: `06_final` directory; metadata is auto-discovered from `work\00_input\metadata.txt`.

Primary outputs: HTML/TSV/optional static plots organized by chart type under `plots\`. The suite writes `plots\index.html` plus one `index.html` inside each chart subdirectory.

Terminal usage:

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

Specify output directory and selected metrics:

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --metadata work\00_input\metadata.txt `
  --output-dir work\06_final\plots `
  --format html `
  --beta-metric braycurtis `
  --beta-metric manhattan `
  --taxonomy-level phylum `
  --taxonomy-level genus
```

Use a custom palette for group-colored charts:

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format svg `
  --color-palette "WT:#4E79A7,KO:#E15759,OE:#59A14F"
```

Skip certain plots:

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --skip-cpcoa `
  --skip-beta-stats
```

`--format png`, `--format pdf`, `--format svg`, or `--format all` require `kaleido` to be installed. The default `html` format does not. All charts use a shared publication-style Plotly theme, sorted metadata groups, and top-N taxonomy filtering with `Others` merging where applicable.

### 5.18 `differential-abundance`

Purpose: Run pairwise taxonomy/feature differential abundance analysis from the final OTU/ASV table and metadata, then generate volcano plots and heatmaps.

Primary inputs: `work\06_final\otutab.txt`, `work\00_input\metadata.txt`, and optional `work\06_final\taxonomy.tsv`.

Primary outputs: `comparison_plan.tsv`, result tables, volcano charts, and heatmaps under `work\06_final\statistics\differential\`.

Terminal usage with explicit comparisons:

```powershell
python process.py differential-abundance `
  --otutab work\06_final\otutab.txt `
  --metadata work\00_input\metadata.txt `
  --taxonomy work\06_final\taxonomy.tsv `
  --compare KO:WT `
  --compare OE:WT `
  --format html
```

Reference-group mode:

```powershell
python process.py differential-abundance `
  --reference-group WT `
  --group-col Group `
  --format html
```

Plan-confirmation mode:

```powershell
python process.py differential-abundance
# edit work\06_final\statistics\differential\comparison_plan.tsv and set Include=yes
python process.py differential-abundance `
  --comparison-plan work\06_final\statistics\differential\comparison_plan.tsv `
  --run-confirmed-plan
```

Direction is always `CASE:CONTROL`; positive `log2FC` means higher mean relative abundance in the case group. The bundled Python implementation supports `wilcox` by default and `t.test` as an option. `edgeR` is not bundled because it requires an R/Bioconductor runtime.

### 5.19 `generate-report` / `report`

Purpose: Generate a standard Markdown and HTML analysis report from a completed `work\06_final` directory.

Primary inputs: `run_summary.json`, optional `provenance.json`, alpha/beta/taxonomy outputs, differential statistics, and visualization files.

Primary outputs: `work\06_final\report\analysis_report.md`, `analysis_report.html`, and `analysis_report_data.json`.

Terminal usage:

```powershell
python process.py generate-report `
  --final-dir work\06_final
```

Alias:

```powershell
python process.py report `
  --final-dir work\06_final
```

Useful options:

```powershell
python process.py generate-report `
  --final-dir work\06_final `
  --output-dir work\06_final\report `
  --top-taxa 10
```

The report separates computational summaries from biological interpretation. The HTML report embeds key Plotly HTML charts when they exist; run `visualization-suite` first to populate the figure section.

### 5.20 Database Registry Commands

Purpose: Manage reference database metadata so runs can report the actual database name, version, taxonomy format, path, and SHA-256 hash.

Primary inputs: `databases.yaml` and local FASTA files under `databas\` or another user-selected directory.

Primary outputs: Terminal check reports and an optional `databases.yaml` registry. `databases.yaml` is local and gitignored; use `databases.example.yaml` as the portable template.

List known databases:

```powershell
python process.py list-databases
```

Check one database by name, alias, or path:

```powershell
python process.py check-database rdp_16s_v18
python process.py check-database databas\rdp_16s_v18.fa --no-hash
```

Register a custom SINTAX database:

```powershell
python process.py register-database `
  --name custom_16s `
  --path databas\custom_16s.fa `
  --version 2026-04 `
  --taxonomy-format sintax `
  --alias custom16s
```

Registered database names can be used in `pipeline_params.yaml` as `annotation_database`, and direct FASTA paths are still supported for compatibility.

### 5.21 `agent-evaluation-log` / `agent-eval-log`

Purpose: Summarize or export Agent task/tool evaluation events recorded during interactive Agent use.

Primary inputs: `run_logs\agent_evaluation_log.jsonl`

Primary outputs: Terminal summary; optional JSON export.

Terminal usage:

```powershell
python process.py agent-evaluation-log
```

Export JSON:

```powershell
python process.py agent-evaluation-log `
  --export-json run_logs\agent_evaluation_log_export.json
```

Use a custom log path:

```powershell
python process.py agent-evaluation-log `
  --log-path run_logs\agent_evaluation_log.jsonl `
  --limit 50
```

The log records user-task turns, tool-call counts, durations, status, failure reasons, and common recovery labels such as `missing_metadata`, `missing_executable`, `bad_tree_path`, and `database_config_error`.

## 6. Single-Chart Python API

`visualization-suite` is the recommended batch entry point. If you only want to generate a specific chart type, you can also call the Python API from the terminal. All commands below can be run directly from the repository root.

All visualization functions accept `output_format='html'`, `'png'`, `'pdf'`, `'svg'`, or `'all'`. Group-colored plots also accept `color_palette='WT:#4E79A7,KO:#E15759,OE:#59A14F'`.

Alpha boxplots:

```powershell
python -c "from src.core.viz_alpha_diversity import plot_alpha_boxplots; plot_alpha_boxplots(alpha_diversity_path='work/06_final/alpha/alpha_diversity.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Alpha grouped barplots:

```powershell
python -c "from src.core.viz_alpha_diversity import plot_alpha_barplots; plot_alpha_barplots(alpha_diversity_path='work/06_final/alpha/alpha_diversity.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Alpha rarefaction curve:

```powershell
python -c "from src.core.viz_alpha_diversity import plot_alpha_rarefaction_curve; plot_alpha_rarefaction_curve(alpha_rarefaction_path='work/06_final/alpha/alpha_rarefaction.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta PCoA:

```powershell
python -c "from src.core.viz_beta_diversity import plot_beta_pcoa; plot_beta_pcoa(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta C-PCoA:

```powershell
python -c "from src.core.viz_beta_diversity import plot_beta_cpcoa; plot_beta_cpcoa(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta distance heatmaps and between-group statistics:

```powershell
python -c "from src.core.viz_beta_diversity import plot_beta_heatmaps; plot_beta_heatmaps(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Taxonomy stacked bar charts:

```powershell
python -c "from src.core.viz_taxonomy import plot_taxonomy_stacked_bars; plot_taxonomy_stacked_bars(taxonomy_summary_dir='work/06_final/taxonomy_summary', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Taxonomy heatmaps:

```powershell
python -c "from src.core.viz_taxonomy import plot_taxonomy_heatmaps; plot_taxonomy_heatmaps(taxonomy_summary_dir='work/06_final/taxonomy_summary', output_format='html')"
```

Differential abundance:

```powershell
python -c "from src.core.stat_taxonomy import run_taxonomy_differential_abundance; run_taxonomy_differential_abundance(comparisons=['KO:WT'], output_format='html')"
```

Analysis report:

```powershell
python -c "from src.core.report_generator import generate_analysis_report; generate_analysis_report(final_dir='work/06_final')"
```

## 7. Agent Tools and Equivalent Terminal Commands

Agent tools are registered in `agent/tools.py`. To view current tools:

```powershell
python agent_cli.py
# then type /tools
```

The table below lists Agent tools and their recommended terminal entry points:

| Agent tool | Recommended terminal entry point |
| --- | --- |
| `run_raw_amplicon_pipeline` | `process.py run-pipeline` or `process.py run-pipeline-config` |
| `run_usearch_unoise3_denoising` | `process.py usearch-asv` |
| `run_usearch_otu_clustering` | `process.py usearch-otu` |
| `run_vsearch_otu_clustering` | `process.py vsearch-otu` |
| `run_vsearch_uchime_ref` | `process.py vsearch-uchime-ref` |
| `run_vsearch_sintax` | `process.py vsearch-sintax` |
| `run_otutab_generation` | `process.py otutab` |
| `run_otutab_filter` | `process.py otutab-filter` |
| `run_otutab_rare` | `process.py otutab-rare` |
| `calculate_alpha_diversity` | `process.py alpha-diversity` |
| `rarefy_otutab` | `process.py otutab-rare` |
| `calculate_richness_rarefaction_curve` | `process.py alpha-diversity --rarefaction-output ... --depth ...` |
| `calculate_rarefaction_curve` | `process.py alpha-diversity --rarefaction-output ... --depth ...` |
| `calculate_beta_distance` | `process.py beta-diversity` |
| `run_phylogenetic_tree_generation` | `process.py phylogenetic-tree` |
| `calculate_group_abundance` | `process.py feature-filter` |
| `parse_sintax_to_dataframe` | `process.py taxonomy-summary --sintax ... --output ...` |
| `summarize_taxa_abundance` | `process.py taxonomy-summary --sintax ... --otutab ... --output ...` |
| `run_visualization_suite` | `process.py visualization-suite` |
| `build_differential_comparison_plan` | `process.py differential-abundance` without `--compare` or `--reference-group` |
| `run_taxonomy_differential_abundance` | `process.py differential-abundance --compare CASE:CONTROL` |
| `plot_differential_volcano` | Python API, see section 6 |
| `plot_differential_heatmap` | Python API, see section 6 |
| `generate_analysis_report` | `process.py generate-report` or `process.py report` |
| `list_registered_databases` | `process.py list-databases` |
| `check_registered_database` | `process.py check-database` |
| `register_database` | `process.py register-database` |
| `list_agent_eval_cases` | Agent-only static evaluation helper |
| `run_agent_eval_cases` | Agent-only static evaluation helper |
| `inspect_optional_skill_dependencies` | Agent-only optional dependency check |
| `summarize_agent_evaluation_log` | `process.py agent-evaluation-log` |
| `export_agent_evaluation_log` | `process.py agent-evaluation-log --export-json ...` |
| `summarize_agent_traces` | Agent-only trace helper; see `run_logs\agent_tool_trace.jsonl` |
| `export_agent_traces` | Agent-only trace helper; see `run_logs\agent_tool_trace.jsonl` |
| `plot_alpha_boxplots` | Python API, see section 6 |
| `plot_alpha_barplots` | Python API, see section 6 |
| `plot_alpha_rarefaction_curve` | Python API, see section 6 |
| `plot_beta_pcoa` | Python API, see section 6 |
| `plot_beta_cpcoa` | Python API, see section 6 |
| `plot_beta_heatmaps` | Python API, see section 6 |
| `plot_taxonomy_stacked_bars` | Python API, see section 6 |
| `plot_taxonomy_heatmaps` | Python API, see section 6 |

The Agent can invoke these tools using natural language, for example:

```text
Run the full pipeline with the current pipeline_params.yaml.
Generate all standard visualization charts for work/06_final.
Generate the final Markdown and HTML analysis report.
Plot beta PCoA and taxonomy stacked bars from the completed run.
```

## 8. Dependencies

Use Python 3.10+ from your active environment. The Windows setup script can also create a local `.venv` or use a bundled runtime when one is provided:

```powershell
python --version
```

### 8.1 Python Packages

Python packages required by the core pipeline, CLI, Agent, and visualization:

| Package | Purpose |
| --- | --- |
| `pyyaml` | Read `pipeline_params.yaml` and `config.yaml` |
| `click` | `process.py` CLI |
| `numpy` | Numerical computation, distance matrices, sampling |
| `pandas` | Table reading, writing, and summarization |
| `scipy` | Clustering, statistics, distance matrix helpers |
| `scikit-bio` | Alpha/beta diversity, UniFrac, PERMANOVA/ANOSIM |
| `biopython` | FASTA/FASTQ processing |
| `pydantic>=2.0` | Parameter and tool schema support |
| `plotly>=5.15` | Interactive HTML charts |
| `rich` | Agent CLI terminal UI |
| `litellm` | Agent calls to OpenAI-compatible LLMs |
| `kaleido` | Optional; only for Plotly static `png`/`pdf`/`svg` export |

Install common Agent and visualization dependencies:

```powershell
python -m pip install litellm rich plotly
```

To export static plots:

```powershell
python -m pip install kaleido
```

A Conda environment file is available at `environment.yml`, which lists the main dependencies.

### 8.2 External Tools

Feature generation, chimera removal, OTU table construction, and annotation in the full pipeline require external executables:

| Tool | Default location or source | Purpose |
| --- | --- | --- |
| USEARCH | `bin/windows/usearch.exe` or `--usearch-path` | UNOISE3, cluster_otus, otutab, otutab_stats, fastx_getseqs |
| VSEARCH | `bin/windows/vsearch.exe` or `--vsearch-path` | cluster_size, uchime_ref, sintax, usearch_global |

### 8.3 Databases

Default built-in compatibility records:

| File | Purpose |
| --- | --- |
| `databas/rdp_16s_v18.fa` | Chimera removal and SINTAX annotation |
| `databas/silva_16s_v123.fa` | Optional SINTAX annotation database |

Large FASTA files are not tracked by Git. Copy `databases.example.yaml` to `databases.yaml` when you want to pin database version, taxonomy format, aliases, and SHA-256 checksums for a local machine:

```powershell
copy databases.example.yaml databases.yaml
python process.py register-database --name rdp_16s_v18 --path databas\rdp_16s_v18.fa --version v18 --overwrite
python process.py check-database rdp_16s_v18
```

`provenance.json` records database metadata for completed runs, including file size and SHA-256 when the file is available.

### 8.4 What Is Not Bundled

The GitHub repository intentionally does not include local run data or large third-party assets:

| Item | Reason | User action |
| --- | --- | --- |
| Raw FASTQ files | Too large and sample-specific | Put your data under `seq\` or another path referenced by `pipeline_params.yaml` |
| RDP/SILVA FASTA databases | Large files and version-specific licensing/distribution choices | Download or prepare locally, then register/check with `process.py check-database` |
| USEARCH binary | License and redistribution restrictions | Download separately and set `usearch_path` if it is not under `bin\windows\` |
| VSEARCH binary | Platform-specific executable | Install/download for Windows and set `vsearch_path` if needed |
| `.env`, `work\`, `run_logs\` | Local secrets and generated outputs | Keep local; these paths are gitignored |

## 9. Agent Configuration

The Agent is configured via `.env`, environment variables, or command-line arguments.

Copy the template:

```powershell
copy .env.example .env
```

Common variables:

| Variable | Description |
| --- | --- |
| `LLM_API_KEY` | OpenAI-compatible API key |
| `LLM_API_BASE` | Proxy or compatible endpoint base URL |
| `DEFAULT_MODEL` | LiteLLM model string |
| `OPENAI_API_KEY` | Fallback key when `LLM_API_KEY` is not set |
| `ANTHROPIC_API_KEY` | Fallback Anthropic key |
| `X_AMPLICON_AGENT_TRACE_PATH` | Optional JSONL path for low-level tool-call traces |
| `X_AMPLICON_AGENT_EVAL_LOG_PATH` | Optional JSONL path for Agent evaluation events |

Override model and endpoint on the command line:

```powershell
python agent_cli.py `
  --model openai/qwen-max `
  --api-key sk-... `
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1
```

View built-in model examples:

```powershell
python agent_cli.py --list-models
```

LLM configuration is optional for the deterministic workflow. Without an API key, use:

```powershell
python process.py cli-only-workflow
```

or start the Agent shell in explicit no-LLM mode:

```powershell
python agent_cli.py --offline
```

In no-LLM mode, local slash commands remain available but natural-language tool calling is disabled. To require a working LLM configuration at startup, use:

```powershell
python agent_cli.py --require-llm
```

## 10. Optional Agent Skills

X-Amplicon can automatically discover extension tools from `agent/skills/*/tools.py`. The current optional skills are:

| Skill | Agent tools | Purpose |
| --- | --- | --- |
| `local_project_rag` | `search_project_files`, `read_project_file`, `read_analysis_summary`, `find_output_artifacts`, `preview_llama_index_documents` | Search README/manuscripts/parameter files, inspect `run_summary.json`, list output artifacts, and optionally preview LlamaIndex documents |
| `agent_tracing` | `summarize_agent_traces`, `export_agent_traces` | Summarize and export Agent tool-call JSONL traces |
| `agent_evaluation` | `list_agent_eval_cases`, `run_agent_eval_cases`, `inspect_optional_skill_dependencies`, `summarize_agent_evaluation_log`, `export_agent_evaluation_log` | Run static Agent checks, inspect optional dependency availability, and summarize/export task/tool evaluation events |
| `literature_evidence` | `search_pubmed_literature`, `fetch_pubmed_abstracts` | Search PubMed through Biopython Entrez; requires network access and `NCBI_EMAIL` |

Install optional skill dependencies:

```powershell
python -m pip install -r requirements-skills.txt
```

Or install them during first-time setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -InstallSkillDeps
```

PubMed search requires `NCBI_EMAIL` in `.env` or in the system environment:

```env
NCBI_EMAIL=your_email@example.com
NCBI_API_KEY=optional-ncbi-api-key
```

List all registered tools:

```powershell
python agent_cli.py
# Then enter /tools
```

Example natural-language requests:

```text
Search the project files for run_summary and summarize the latest output.
Summarize recent agent tool traces.
Run the built-in agent evaluation cases.
Summarize the agent evaluation log and show common recovery paths.
Search PubMed for recent 16S microbiome benchmark papers.
```

Online literature retrieval is intended for source-backed background and references. It does not replace benchmark validation of the current project.

## 11. Troubleshooting

Start with this quick table, then use the detailed sections below:

| Symptom | First command to run | Likely fix |
| --- | --- | --- |
| Pipeline fails before analysis starts | `python process.py check-pipeline-config --params pipeline_params.yaml` | Fix missing metadata, FASTQ paths, executables, or database paths |
| Samples are not found | `python process.py check-pipeline-config --params pipeline_params.yaml` | Align `SampleID`, `read1_suffix`, and `read2_suffix` with actual FASTQ filenames |
| USEARCH/VSEARCH not found | `python process.py check-pipeline-config --params pipeline_params.yaml` | Set `usearch_path` and `vsearch_path` in `pipeline_params.yaml` |
| SINTAX or chimera database missing | `python process.py check-database rdp_16s_v18` | Register the database or use a direct FASTA path |
| No plots are generated | `python process.py visualization-suite --final-dir work\06_final --format html` | Run visualization after the full pipeline; install `kaleido` only for static formats |
| Agent cannot call tools in natural language | `python agent_cli.py --offline` | Use CLI-only mode or configure a valid LLM API key |

### 11.1 Check `run_summary.json` First

After the full pipeline completes or fails, check this file first:

```text
work\06_final\run_summary.json
```

It is more suitable than scrolling terminal logs for automated reporting and debugging.

### 11.2 USEARCH or VSEARCH Not Found

First run:

```powershell
python process.py check-pipeline-config --params pipeline_params.yaml
```

If the executable is reported as unavailable, set `usearch_path` and `vsearch_path` in `pipeline_params.yaml`, or pass them on the command line:

```powershell
--usearch-path bin\windows\usearch.exe --vsearch-path bin\windows\vsearch.exe
```

### 11.3 Sample Matching Failure

Check three things:

- Whether the first column or `SampleID` column of metadata matches the FASTQ sample prefixes.
- Whether `read1_suffix` and `read2_suffix` match the actual filenames.
- Whether `seq_dir` points to the correct FASTQ directory.

### 11.4 No UniFrac Output

The full pipeline automatically generates `otus.tree` from `work\06_final\otus.fa`. If running `beta-diversity` standalone, you must explicitly provide:

```powershell
--tree work\06_final\otus.tree
```

### 11.5 No PNG/PDF/SVG Visualization Output

The default `html` format requires no additional dependencies. For static plots, install:

```powershell
python -m pip install kaleido
```

Then run:

```powershell
python process.py visualization-suite `
  --final-dir work\06_final `
  --format all
```

### 11.6 When to Use the Agent vs. the CLI

- For stable reproduction or scripting: prefer `process.py`.
- To let the system choose steps, interpret results, or automatically generate charts based on natural language: use `agent_cli.py`.
- To verify everything is ready before a run: use `check-pipeline-config`.
- To summarize a completed run: read `run_summary.json`, then run `visualization-suite` as needed.

## 12. Windows Distribution Options

X-Amplicon currently supports three Windows-oriented distribution routes. See
[docs/windows_distribution.md](docs/windows_distribution.md) for the full checklist.

| Route | Best for | Main command |
| --- | --- | --- |
| Source install | GitHub users and developers | `powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1` |
| Conda/mamba environment | Bioinformatics users who already use conda | `mamba env create -f environment.yml` |
| Portable bundle | Non-developer Windows users | `.\run_process.bat --help` after extracting a prepared bundle |

`setup_windows.ps1` now provides distribution-oriented checks and outputs:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -DiagnosticsOnly
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -CreateDesktopShortcuts
```

The diagnostics report is written to:

```text
run_logs/windows_setup_diagnostics.json
```

Public GitHub releases should not include `.env`, `work\`, `run_logs\`, `seq\`,
`databas\`, `bin\`, `.venv\`, or `.tools\`. Private lab bundles may include
database and executable folders only when licensing and local policy allow it.

