[English](README.md) | [中文](README_zh.md)

# X-Amplicon

X-Amplicon is a Python workflow and AI Agent for 16S rRNA amplicon paired-end sequencing data. Starting from raw paired-end FASTQ files and a metadata table, it performs read merging, quality control, dereplication, OTU/ASV generation, chimera removal, OTU table construction, taxonomic annotation, filtering, rarefaction, alpha/beta diversity analysis, and taxonomy summary — and then generates alpha, beta, and taxonomy visualization plots after the full analysis completes.

The recommended entry point is `process.py run-pipeline-config`, with parameters managed by `pipeline_params.yaml`. Agent mode is launched via `agent_cli.py`, which internally calls the same set of core tools.

All command examples assume you are running from the repository root directory:

```powershell
cd D:\16s_translate\X-Amplicon
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

If you need to export `png`, `pdf`, or `all` static plots, add `-InstallStaticExport` to install `kaleido`:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -UseChinaMirror -InstallStaticExport
```

### 1.1 Check Configuration

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config --params pipeline_params.yaml
```

This command only validates parameters, input paths, sample matching, and external executables — it does not start any time-consuming analysis.

Equivalent pre-check entry point:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml --check-only
```

`--dry-run` is an alias for `--check-only`.

### 1.2 Run the Full Pipeline

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config --params pipeline_params.yaml
```

### 1.3 Generate Standard Visualizations

Run after the full pipeline completes:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

Plot output defaults to `work\06_final\plots\`, with each chart type placed in its own subdirectory.

### 1.4 Launch the Agent

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py
```

Common interactive commands:

| Command | Description |
| --- | --- |
| `/tools` | List tools available to the Agent |
| `/params` | View current pipeline parameters |
| `/language` | Switch CLI language; enter `Chinese` or `English` |
| `/status` | View session status |
| `/report` | Generate a Markdown analysis report |
| `/config` | View model and API configuration |
| `/quit` | Exit |

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
| `reference_db` | Reference chimera-checking database FASTA |
| `otutab_method` | `usearch` or `vsearch` |
| `annotation_database` | `rdp_16s_v18` or `silva_16s_v123` |
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
12. If plots are needed, generate visualizations separately via `visualization-suite` or Agent tools.

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
      alpha_boxplot_chart/
      alpha_barplot_chart/
      alpha_rare_chart/
      beta_pcoa_chart/
      beta_cpcoa_chart/
      beta_heatmap_chart/
      taxonomy_stacked_bar_chart/
      taxonomy_heatmap_chart/
```

`run_summary.json` is a machine-readable summary of the full pipeline run. It should be the first file checked by both the Agent and for manual troubleshooting. It records effective parameters, executed steps, key outputs, rarefaction depth, beta metrics, tree file path, and failure information.

`beta/` outputs `braycurtis`, `jaccard`, `euclidean`, and `manhattan` by default. `cityblock` is accepted only as a compatibility alias; all documentation and output filenames use `manhattan`.

## 5. CLI Overview

List all subcommands:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py --help
```

View options for a specific subcommand:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py beta-diversity --help
```

Each module below is described with: purpose, primary inputs, primary outputs, and terminal usage.

### 5.1 `check-pipeline-config`

Purpose: Validate `pipeline_params.yaml`, input files, sample matching, databases, and USEARCH/VSEARCH executables.

Primary inputs: `pipeline_params.yaml`

Primary outputs: Terminal validation report; no analysis results written.

Terminal usage:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config `
  --params pipeline_params.yaml
```

### 5.2 `run-pipeline-config`

Purpose: Run the complete 16S analysis pipeline using YAML parameters.

Primary inputs: `pipeline_params.yaml`

Primary outputs: `output_root\06_final\` and `run_summary.json`

Terminal usage:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config `
  --params pipeline_params.yaml
```

Check without running:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline-config `
  --params pipeline_params.yaml `
  --check-only
```

### 5.3 `run-pipeline`

Purpose: Run the full pipeline by passing parameters directly on the command line, without a YAML file. Useful for overriding parameters on the fly or scripted runs.

Primary inputs: metadata, FASTQ directory, filter parameters, and pipeline parameters.

Primary outputs: Complete staged output under `--output-root`.

Terminal usage:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py run-pipeline `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py usearch-asv `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py usearch-otu `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py vsearch-otu `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py vsearch-uchime-ref `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py otutab `
  --input work\02_filtered\filtered.fa `
  --representatives work\04_features\otus.fa `
  --output work\05_raw_results `
  --method usearch `
  --threads 4
```

Using the VSEARCH backend:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py otutab `
  --input work\02_filtered\filtered.fa `
  --representatives work\04_features\otus.fa `
  --output work\05_raw_results `
  --method vsearch `
  --identity 0.97 `
  --threads 4
```

### 5.9 `vsearch-sintax`

Purpose: Taxonomically annotate representative sequences using VSEARCH SINTAX.

Primary inputs: OTU/ASV representative FASTA.

Primary outputs: `otus.sintax`.

Terminal usage:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py vsearch-sintax `
  --input work\04_features\otus.fa `
  --output work\05_raw_results `
  --database rdp_16s_v18 `
  --sintax-cutoff 0.1 `
  --threads 4
```

### 5.10 `otutab-filter`

Purpose: Filter the feature table and representative sequences by taxonomy route.

Primary inputs: Raw OTU table, SINTAX annotations, representative sequences FASTA.

Primary outputs: Filtered `otutab.txt`, `otus.fa`, `otus.sintax`, feature ID list, and statistics table.

Terminal usage:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py otutab-filter `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py otutab-rare `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py alpha-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\alpha\alpha_diversity.tsv
```

With rarefaction curve:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py alpha-diversity `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py beta-diversity `
  --input work\06_final\otutab.txt `
  --output work\06_final\beta `
  --metric braycurtis `
  --metric jaccard `
  --metric euclidean `
  --metric manhattan
```

Calculate UniFrac:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py beta-diversity `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py phylogenetic-tree `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py taxonomy-summary `
  --sintax work\06_final\otus.sintax `
  --otutab work\06_final\otutab.txt `
  --output work\06_final
```

Summarize only selected ranks:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py taxonomy-summary `
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
& .\.tools\python-3.13.13-amd64\python.exe process.py feature-filter `
  --input work\06_final\otutab.txt `
  --metadata metadata.txt `
  --group-col Group `
  --threshold 0.001 `
  --output work\06_final\group_abundance.tsv
```

Note: `feature-filter` is a standalone analysis command and is not executed automatically by `run-pipeline-config`.

### 5.17 `visualization-suite`

Purpose: Batch-generate standard plots from the `06_final` output of the full pipeline.

Primary inputs: `06_final` directory; metadata is auto-discovered from `work\00_input\metadata.txt`.

Primary outputs: HTML/TSV/optional static plots organized by chart type under `plots\`.

Terminal usage:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite `
  --final-dir work\06_final `
  --format html
```

Specify output directory and selected metrics:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite `
  --final-dir work\06_final `
  --metadata work\00_input\metadata.txt `
  --output-dir work\06_final\plots `
  --format html `
  --beta-metric braycurtis `
  --beta-metric manhattan `
  --taxonomy-level phylum `
  --taxonomy-level genus
```

Skip certain plots:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite `
  --final-dir work\06_final `
  --skip-cpcoa `
  --skip-beta-stats
```

`--format png`, `--format pdf`, or `--format all` require `kaleido` to be installed. The default `html` format does not.

## 6. Single-Chart Python API

`visualization-suite` is the recommended batch entry point. If you only want to generate a specific chart type, you can also call the Python API from the terminal. All commands below can be run directly from the repository root.

Alpha boxplots:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_alpha_diversity import plot_alpha_boxplots; plot_alpha_boxplots(alpha_diversity_path='work/06_final/alpha/alpha_diversity.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Alpha grouped barplots:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_alpha_diversity import plot_alpha_barplots; plot_alpha_barplots(alpha_diversity_path='work/06_final/alpha/alpha_diversity.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Alpha rarefaction curve:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_alpha_diversity import plot_alpha_rarefaction_curve; plot_alpha_rarefaction_curve(alpha_rarefaction_path='work/06_final/alpha/alpha_rarefaction.tsv', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta PCoA:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_beta_diversity import plot_beta_pcoa; plot_beta_pcoa(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta C-PCoA:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_beta_diversity import plot_beta_cpcoa; plot_beta_cpcoa(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Beta distance heatmaps and between-group statistics:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_beta_diversity import plot_beta_heatmaps; plot_beta_heatmaps(beta_dir='work/06_final/beta', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Taxonomy stacked bar charts:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_taxonomy import plot_taxonomy_stacked_bars; plot_taxonomy_stacked_bars(taxonomy_summary_dir='work/06_final/taxonomy_summary', metadata_path='work/00_input/metadata.txt', output_format='html')"
```

Taxonomy heatmaps:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -c "from src.core.viz_taxonomy import plot_taxonomy_heatmaps; plot_taxonomy_heatmaps(taxonomy_summary_dir='work/06_final/taxonomy_summary', output_format='html')"
```

## 7. Agent Tools and Equivalent Terminal Commands

Agent tools are registered in `agent/tools.py`. To view current tools:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py
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
Plot beta PCoA and taxonomy stacked bars from the completed run.
```

## 8. Dependencies

It is recommended to use the Python interpreter bundled in the repository:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe --version
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
| `kaleido` | Optional; only for Plotly static `png`/`pdf` export |

Install common Agent and visualization dependencies:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -m pip install litellm rich plotly
```

To export static plots:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -m pip install kaleido
```

A Conda environment file is available at `environment.yml`, which lists the main dependencies.

### 8.2 External Tools

Feature generation, chimera removal, OTU table construction, and annotation in the full pipeline require external executables:

| Tool | Default location or source | Purpose |
| --- | --- | --- |
| USEARCH | `bin/windows/usearch.exe` or `--usearch-path` | UNOISE3, cluster_otus, otutab, otutab_stats, fastx_getseqs |
| VSEARCH | `bin/windows/vsearch.exe` or `--vsearch-path` | cluster_size, uchime_ref, sintax, usearch_global |

### 8.3 Databases

Default database files:

| File | Purpose |
| --- | --- |
| `databas/rdp_16s_v18.fa` | Chimera removal and SINTAX annotation |
| `databas/silva_16s_v123.fa` | Optional SINTAX annotation database |

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

Override model and endpoint on the command line:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py `
  --model openai/qwen-max `
  --api-key sk-... `
  --api-base https://dashscope.aliyuncs.com/compatible-mode/v1
```

View built-in model examples:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe agent_cli.py --list-models
```

## 10. Troubleshooting

### 10.1 Check `run_summary.json` First

After the full pipeline completes or fails, check this file first:

```text
work\06_final\run_summary.json
```

It is more suitable than scrolling terminal logs for automated reporting and debugging.

### 10.2 USEARCH or VSEARCH Not Found

First run:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py check-pipeline-config --params pipeline_params.yaml
```

If the executable is reported as unavailable, set `usearch_path` and `vsearch_path` in `pipeline_params.yaml`, or pass them on the command line:

```powershell
--usearch-path bin\windows\usearch.exe --vsearch-path bin\windows\vsearch.exe
```

### 10.3 Sample Matching Failure

Check three things:

- Whether the first column or `SampleID` column of metadata matches the FASTQ sample prefixes.
- Whether `read1_suffix` and `read2_suffix` match the actual filenames.
- Whether `seq_dir` points to the correct FASTQ directory.

### 10.4 No UniFrac Output

The full pipeline automatically generates `otus.tree` from `work\06_final\otus.fa`. If running `beta-diversity` standalone, you must explicitly provide:

```powershell
--tree work\06_final\otus.tree
```

### 10.5 No PNG/PDF Visualization Output

The default `html` format requires no additional dependencies. For static plots, install:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe -m pip install kaleido
```

Then run:

```powershell
& .\.tools\python-3.13.13-amd64\python.exe process.py visualization-suite `
  --final-dir work\06_final `
  --format all
```

### 10.6 When to Use the Agent vs. the CLI

- For stable reproduction or scripting: prefer `process.py`.
- To let the system choose steps, interpret results, or automatically generate charts based on natural language: use `agent_cli.py`.
- To verify everything is ready before a run: use `check-pipeline-config`.
- To summarize a completed run: read `run_summary.json`, then run `visualization-suite` as needed.
