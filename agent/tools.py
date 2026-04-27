"""Tool registry: wraps src/core functions as OpenAI-compatible function-calling tools.

Each public function from src/core is wrapped with:
- A JSON schema derived from its type hints and docstring.
- A safe executor that catches exceptions (including missing-executable errors)
  and returns a structured result dict instead of raising.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Raw function imports - grouped by priority
# ---------------------------------------------------------------------------

# Priority 1: pure-Python modules (no external executable dependency)
from src.core.alpha_diversity import (
    calculate_alpha_diversity,
    calculate_rarefaction_curve,
    calculate_richness_rarefaction_curve,
    rarefy_otutab,
)
from src.core.beta_diversity import calculate_beta_distance
from src.core.feature_filter import calculate_group_abundance
from src.core.taxonomy_summary import parse_sintax_to_dataframe, summarize_taxa_abundance

# Priority 2: workflow modules that wrap external executables
from src.core.otu_table_generator import run_otutab_generation
from src.core.otutab_filter import run_otutab_filter
from src.core.otutab_rare import run_otutab_rare
from src.core.phylogenetic_tree import run_phylogenetic_tree_generation
from src.core.raw_amplicon_pipeline import run_raw_amplicon_pipeline
from src.core.usearch_ASV_unoise3 import run_usearch_unoise3_denoising
from src.core.usearch_otu_cluster import run_usearch_otu_clustering
from src.core.vsearch_otu_cluster import run_vsearch_otu_clustering
from src.core.vsearch_sintax import run_vsearch_sintax
from src.core.vsearch_uchime_ref import run_vsearch_uchime_ref


def _load_visualization_tool_definitions() -> list[dict[str, Any]]:
    """Discover tool definitions exported by src.core.viz_* modules."""

    import src.core as core_package

    definitions: list[dict[str, Any]] = []
    for module_info in pkgutil.iter_modules(core_package.__path__):
        module_name = module_info.name
        if not module_name.startswith("viz_") or module_name == "viz_common":
            continue

        module = importlib.import_module(f"src.core.{module_name}")
        module_definitions = getattr(module, "TOOL_DEFINITIONS", [])
        if not isinstance(module_definitions, list):
            continue
        for definition in module_definitions:
            if isinstance(definition, dict):
                definitions.append(definition)

    return definitions


def _load_skill_tool_definitions() -> list[dict[str, Any]]:
    """Discover tool definitions exported by agent.skills.*.tools modules."""

    try:
        import agent.skills as skills_package
    except ModuleNotFoundError:
        return []

    definitions: list[dict[str, Any]] = []
    for module_info in pkgutil.iter_modules(skills_package.__path__):
        skill_name = module_info.name
        try:
            module = importlib.import_module(f"agent.skills.{skill_name}.tools")
        except ModuleNotFoundError:
            continue
        module_definitions = getattr(module, "TOOL_DEFINITIONS", [])
        if not isinstance(module_definitions, list):
            continue
        for definition in module_definitions:
            if isinstance(definition, dict):
                definitions.append(definition)

    return definitions

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------
# Each entry is a dict with keys:
#   name        - function name used in LLM tool calls
#   description - what this tool does in the 16S workflow context
#   parameters  - OpenAI-compatible JSON Schema object
#   fn          - the actual callable
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    # ------------------------------------------------------------------
    # PRIORITY 1 - Pure Python
    # ------------------------------------------------------------------
    {
        "name": "calculate_alpha_diversity",
        "description": (
            "16S Step 6a - Alpha diversity. "
            "Calculates per-sample alpha diversity metrics (Observed OTUs, Shannon, "
            "Simpson, Chao1, ACE) from a rarefied OTU table (pandas DataFrame). "
            "Returns a DataFrame indexed by SampleID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": (
                        "OTU table as a pandas DataFrame. Rows are OTU IDs, "
                        "columns are sample IDs, values are integer read counts."
                    ),
                },
            },
            "required": ["otutab"],
        },
        "fn": calculate_alpha_diversity,
    },
    {
        "name": "rarefy_otutab",
        "description": (
            "16S Step 5b - Rarefaction. "
            "Rarefies an OTU table to an equal sequencing depth across all samples. "
            "Samples below the resolved depth are discarded. "
            "Returns (rarefied_table, resolved_depth, discarded_samples)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": "OTU table DataFrame (OTU IDs x sample IDs, integer counts).",
                },
                "depth": {
                    "type": "integer",
                    "description": "Rarefaction depth. Use 0 to auto-select the minimum sample depth.",
                    "default": 0,
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility.",
                    "default": 1,
                },
            },
            "required": ["otutab"],
        },
        "fn": rarefy_otutab,
    },
    {
        "name": "calculate_richness_rarefaction_curve",
        "description": (
            "16S Step 6b - Richness rarefaction curve. "
            "Generates a USEARCH-style rarefaction curve showing observed OTU richness "
            "at 1-100% subsampling depths for each sample. "
            "Returns a wide-format DataFrame (index=percentage, columns=sample IDs)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": "OTU table DataFrame (OTU IDs x sample IDs, integer counts).",
                },
                "percentages": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Integer percentages (1-100) at which to subsample. Defaults to 1-100.",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility.",
                    "default": 1,
                },
            },
            "required": ["otutab"],
        },
        "fn": calculate_richness_rarefaction_curve,
    },
    {
        "name": "calculate_rarefaction_curve",
        "description": (
            "16S Step 6c - Full rarefaction curve (all alpha metrics). "
            "Calculates rarefaction curves for all alpha diversity metrics "
            "(Observed OTUs, Shannon, Simpson, Chao1, ACE) at specified read depths. "
            "Returns a long-format DataFrame with columns SampleID, Depth, and metric values."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": "OTU table DataFrame (OTU IDs x sample IDs, integer counts).",
                },
                "depths": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of positive integer read depths at which to evaluate diversity.",
                },
            },
            "required": ["otutab", "depths"],
        },
        "fn": calculate_rarefaction_curve,
    },
    {
        "name": "calculate_beta_distance",
        "description": (
            "16S Step 7 - Beta diversity distance matrix. "
            "Computes a sample-by-sample distance matrix using Bray-Curtis, Jaccard, "
            "Euclidean, Manhattan, unweighted UniFrac, or weighted UniFrac. "
            "UniFrac metrics require a phylogenetic tree (skbio.TreeNode). "
            "Returns a symmetric DataFrame indexed and columned by sample ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": "OTU table DataFrame (OTU IDs x sample IDs, numeric counts).",
                },
                "metric": {
                    "type": "string",
                    "enum": [
                        "braycurtis",
                        "jaccard",
                        "euclidean",
                        "manhattan",
                        "unweighted_unifrac",
                        "weighted_unifrac",
                    ],
                    "description": "Distance metric to use.",
                },
                "tree": {
                    "type": "object",
                    "description": (
                        "Rooted phylogenetic tree as a skbio.TreeNode. "
                        "Required only for unweighted_unifrac and weighted_unifrac."
                    ),
                },
            },
            "required": ["otutab", "metric"],
        },
        "fn": calculate_beta_distance,
    },
    {
        "name": "run_phylogenetic_tree_generation",
        "description": (
            "16S Step 7a - Phylogenetic tree generation. "
            "Builds a rooted Newick OTU/ASV tree from representative sequences "
            "without calling USEARCH. The full raw pipeline runs this automatically "
            "before UniFrac beta diversity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Representative OTU/ASV FASTA file, usually work/06_final/otus.fa.",
                },
                "output_tree_path": {
                    "type": "string",
                    "description": "Output Newick tree path, usually work/06_final/otus.tree.",
                },
                "linkage": {
                    "type": "string",
                    "enum": ["max", "min", "avg"],
                    "description": "Agglomerative linkage method. Defaults to max, matching USEARCH cluster_agg.",
                    "default": "max",
                },
                "distance_method": {
                    "type": "string",
                    "enum": ["p_distance"],
                    "description": "Pairwise sequence distance method. Defaults to gap-aware p-distance.",
                    "default": "p_distance",
                },
            },
            "required": ["input_fasta", "output_tree_path"],
        },
        "fn": run_phylogenetic_tree_generation,
    },
    {
        "name": "calculate_group_abundance",
        "description": (
            "16S Step 8 - Group-level abundance filtering. "
            "Calculates group mean relative abundance (%) per OTU, grouped by a metadata "
            "column, and filters out OTUs below a minimum abundance threshold. "
            "Replaces the original Rscript otu_mean.R step. "
            "Returns a DataFrame of filtered OTUs x groups with relative abundance values."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": "OTU table DataFrame (OTU IDs x sample IDs, numeric counts).",
                },
                "metadata": {
                    "type": "object",
                    "description": (
                        "Sample metadata DataFrame. Index must match OTU table columns, "
                        "or must contain a SampleID column."
                    ),
                },
                "group_col": {
                    "type": "string",
                    "description": "Metadata column name used to group samples (e.g. 'Group', 'Treatment').",
                },
                "threshold": {
                    "type": "number",
                    "description": (
                        "Minimum group mean relative abundance as a fraction. "
                        "0.001 means 0.1%. OTUs below this in all groups are removed."
                    ),
                    "default": 0.001,
                },
            },
            "required": ["otutab", "metadata", "group_col"],
        },
        "fn": calculate_group_abundance,
    },
    {
        "name": "parse_sintax_to_dataframe",
        "description": (
            "16S Step 9a - Parse taxonomy annotation. "
            "Parses a VSEARCH sintax output file (otus.sintax) into a standardized "
            "8-column taxonomy DataFrame: OTUID, Kingdom, Phylum, Class, Order, "
            "Family, Genus, Species. Missing ranks are filled with 'Unassigned'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sintax_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the otus.sintax file.",
                },
            },
            "required": ["sintax_path"],
        },
        "fn": parse_sintax_to_dataframe,
    },
    {
        "name": "summarize_taxa_abundance",
        "description": (
            "16S Step 9b - Taxonomy abundance summary. "
            "Summarizes OTU abundance by a selected taxonomy rank (e.g. Phylum, Genus). "
            "Returns a DataFrame indexed by taxon label with per-sample relative abundance "
            "percentages and an 'All' column showing overall assignment rates."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "otutab": {
                    "type": "object",
                    "description": "OTU table DataFrame (OTU IDs x sample IDs, numeric counts).",
                },
                "taxonomy": {
                    "type": "object",
                    "description": (
                        "Taxonomy DataFrame produced by parse_sintax_to_dataframe, "
                        "containing OTUID plus standard rank columns."
                    ),
                },
                "rank": {
                    "type": "string",
                    "enum": ["Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species"],
                    "description": "Taxonomy rank at which to summarize abundance.",
                },
            },
            "required": ["otutab", "taxonomy", "rank"],
        },
        "fn": summarize_taxa_abundance,
    },

    # ------------------------------------------------------------------
    # PRIORITY 2 - External executable wrappers
    # ------------------------------------------------------------------
    {
        "name": "run_otutab_generation",
        "description": (
            "16S Step 4 - OTU/feature table generation. "
            "Maps quality-filtered reads back to representative sequences (OTUs/ASVs) "
            "using USEARCH (-otutab) or VSEARCH (--usearch_global) to produce a "
            "read-count feature table. Requires USEARCH or VSEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Path to the merged, quality-filtered reads FASTA file.",
                },
                "representative_fasta": {
                    "type": "string",
                    "description": "Path to the representative OTU/ASV sequences FASTA file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory where the output feature table will be written.",
                },
                "method": {
                    "type": "string",
                    "enum": ["usearch", "vsearch"],
                    "description": "Mapping tool to use. Defaults to 'vsearch'.",
                    "default": "vsearch",
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads.",
                    "default": 1,
                },
                "identity": {
                    "type": "number",
                    "description": "Minimum identity threshold (0-1). Defaults to config value (0.97).",
                },
                "tool_path": {
                    "type": "string",
                    "description": "Explicit path to the USEARCH or VSEARCH executable (optional).",
                },
                "output_table_path": {
                    "type": "string",
                    "description": "Override output file path for the feature table (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_fasta", "representative_fasta", "output_dir"],
        },
        "fn": run_otutab_generation,
    },
    {
        "name": "run_otutab_filter",
        "description": (
            "16S Step 5a - Taxonomy-based feature table filtering. "
            "Filters an OTU/ASV feature table by taxonomy route: "
            "'16s' keeps only Bacteria/Archaea and removes Chloroplast/Mitochondria; "
            "'its' keeps only Fungi; 'none' passes through without filtering. "
            "Requires USEARCH executable for sequence extraction."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_table": {
                    "type": "string",
                    "description": "Path to the raw feature table (tab-separated, #OTUID header).",
                },
                "taxonomy_path": {
                    "type": "string",
                    "description": "Path to the sintax taxonomy annotation file.",
                },
                "representative_fasta": {
                    "type": "string",
                    "description": "Path to the representative sequences FASTA file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for filtered output files.",
                },
                "route": {
                    "type": "string",
                    "enum": ["16s", "its", "none"],
                    "description": "Filtering route: '16s', 'its', or 'none'.",
                },
                "usearch_path": {
                    "type": "string",
                    "description": "Explicit path to the USEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_table", "taxonomy_path", "representative_fasta", "output_dir", "route"],
        },
        "fn": run_otutab_filter,
    },
    {
        "name": "run_otutab_rare",
        "description": (
            "16S Step 5c - OTU table rarefaction workflow (file-based). "
            "Reads an OTU table from disk, rarefies to equal depth, writes the rarefied "
            "table and alpha diversity metrics to files, and runs USEARCH otutab_stats. "
            "Use rarefy_otutab + calculate_alpha_diversity for in-memory DataFrame operations. "
            "Requires USEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_table": {
                    "type": "string",
                    "description": "Path to the input OTU table file.",
                },
                "depth": {
                    "type": "integer",
                    "description": "Rarefaction depth. Use 0 to auto-select minimum sample depth.",
                    "default": 0,
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility.",
                    "default": 1,
                },
                "normalize_path": {
                    "type": "string",
                    "description": "Override output path for the rarefied table (optional).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Override output path for the alpha diversity table (optional).",
                },
                "stats_path": {
                    "type": "string",
                    "description": "Override output path for the OTU table stats file (optional).",
                },
                "usearch_path": {
                    "type": "string",
                    "description": "Explicit path to the USEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_table"],
        },
        "fn": run_otutab_rare,
    },
    {
        "name": "run_vsearch_sintax",
        "description": (
            "16S Step 3b - Taxonomy classification with VSEARCH SINTAX. "
            "Classifies representative OTU/ASV sequences against a reference database "
            "(RDP 16S v18 or SILVA 16S v123) using the SINTAX algorithm. "
            "Produces an otus.sintax annotation file. Requires VSEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Path to the representative OTU/ASV sequences FASTA file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for the sintax output file.",
                },
                "database": {
                    "type": "string",
                    "enum": ["rdp_16s_v18", "silva_16s_v123"],
                    "description": "Reference database. Defaults to 'rdp_16s_v18'.",
                    "default": "rdp_16s_v18",
                },
                "sintax_cutoff": {
                    "type": "number",
                    "description": "Bootstrap confidence cutoff (0-1). Defaults to 0.1.",
                    "default": 0.1,
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads.",
                    "default": 1,
                },
                "vsearch_path": {
                    "type": "string",
                    "description": "Explicit path to the VSEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_fasta", "output_dir"],
        },
        "fn": run_vsearch_sintax,
    },
    {
        "name": "run_vsearch_otu_clustering",
        "description": (
            "16S Step 3a - OTU clustering with VSEARCH. "
            "Clusters unique sequences into OTUs at a specified identity threshold "
            "(default 97%) using VSEARCH cluster_size. Produces representative OTU "
            "sequences and a chimera-checked FASTA. Requires VSEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Path to the dereplicated unique sequences FASTA file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for OTU clustering output files.",
                },
                "identity": {
                    "type": "number",
                    "description": "Clustering identity threshold (0-1). Defaults to 0.97.",
                },
                "minsize": {
                    "type": "integer",
                    "description": "Minimum cluster size to retain. Defaults to 1.",
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads.",
                    "default": 1,
                },
                "vsearch_path": {
                    "type": "string",
                    "description": "Explicit path to the VSEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_fasta", "output_dir"],
        },
        "fn": run_vsearch_otu_clustering,
    },
    {
        "name": "run_vsearch_uchime_ref",
        "description": (
            "16S Step 2b - Reference-based chimera removal with VSEARCH uchime_ref. "
            "Removes chimeric sequences from a FASTA file by comparing against the "
            "RDP 16S reference database. Produces a non-chimeric FASTA. "
            "Requires VSEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Path to the input sequences FASTA file to screen for chimeras.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for chimera-filtered output files.",
                },
                "chimera_mode": {
                    "type": "string",
                    "enum": ["ref", "none"],
                    "description": "'ref' runs uchime_ref filtering; 'none' copies input unchanged.",
                    "default": "ref",
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads.",
                    "default": 1,
                },
                "vsearch_path": {
                    "type": "string",
                    "description": "Explicit path to the VSEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_fasta", "output_dir"],
        },
        "fn": run_vsearch_uchime_ref,
    },
    {
        "name": "run_usearch_unoise3_denoising",
        "description": (
            "16S Step 3a (ASV route) - ASV denoising with USEARCH UNOISE3. "
            "Denoises unique sequences into Amplicon Sequence Variants (ASVs/ZOTUs) "
            "using the UNOISE3 algorithm. Alternative to OTU clustering for higher "
            "resolution analysis. Requires USEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Path to the dereplicated unique sequences FASTA file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for ASV denoising output files.",
                },
                "minsize": {
                    "type": "integer",
                    "description": "Minimum abundance to retain a unique sequence. Defaults to 10.",
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads.",
                    "default": 1,
                },
                "usearch_path": {
                    "type": "string",
                    "description": "Explicit path to the USEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_fasta", "output_dir"],
        },
        "fn": run_usearch_unoise3_denoising,
    },
    {
        "name": "run_usearch_otu_clustering",
        "description": (
            "16S Step 3a (USEARCH OTU route) - OTU clustering with USEARCH cluster_otus. "
            "Clusters unique sequences into OTUs at 97% identity using USEARCH. "
            "Alternative to VSEARCH clustering. Requires USEARCH executable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "input_fasta": {
                    "type": "string",
                    "description": "Path to the dereplicated unique sequences FASTA file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory for OTU clustering output files.",
                },
                "minsize": {
                    "type": "integer",
                    "description": "Minimum abundance to retain a unique sequence. Defaults to 10.",
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads.",
                    "default": 1,
                },
                "usearch_path": {
                    "type": "string",
                    "description": "Explicit path to the USEARCH executable (optional).",
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for the external command (optional).",
                },
            },
            "required": ["input_fasta", "output_dir"],
        },
        "fn": run_usearch_otu_clustering,
    },
    {
        "name": "run_raw_amplicon_pipeline",
        "description": (
            "16S Full Pipeline - End-to-end raw FASTQ analysis. "
            "Runs the complete integrated pipeline from raw paired-end FASTQ files through "
            "merging, quality filtering, dereplication, feature generation (ASV denoising "
            "via USEARCH UNOISE3, or OTU clustering via USEARCH/VSEARCH), chimera removal, "
            "OTU table generation, taxonomy annotation (VSEARCH SINTAX), taxonomy-based "
            "filtering, rarefaction, alpha diversity, beta diversity, and taxonomy summaries. "
            "Requires both USEARCH and VSEARCH executables. "
            "Writes a run_summary.json to output_root/06_final/."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metadata_path": {
                    "type": "string",
                    "description": (
                        "Path to the sample metadata TSV file. Must contain a SampleID column "
                        "and columns matching read1/read2 file names."
                    ),
                },
                "seq_dir": {
                    "type": "string",
                    "description": "Directory containing the raw paired-end FASTQ files.",
                },
                "output_root": {
                    "type": "string",
                    "description": "Root output directory. Subdirectories 00_input through 06_final are created automatically.",
                },
                "fastq_stripleft": {
                    "type": "integer",
                    "description": "Number of bases to strip from the left (5') end of each read (primer length).",
                },
                "fastq_stripright": {
                    "type": "integer",
                    "description": "Number of bases to strip from the right (3') end of each read.",
                },
                "fastq_maxee_rate": {
                    "type": "number",
                    "description": "Maximum expected error rate per base for quality filtering (e.g. 0.01 = 1%).",
                },
                "feature_minsize": {
                    "type": "integer",
                    "description": "Minimum abundance for a unique sequence to be retained before feature generation. Defaults to 10.",
                    "default": 10,
                },
                "feature_method": {
                    "type": "string",
                    "enum": ["usearch-asv", "usearch-otu", "vsearch-otu"],
                    "description": "Feature generation method: ASV denoising (usearch-asv) or OTU clustering (usearch-otu / vsearch-otu). Defaults to 'usearch-asv'.",
                    "default": "usearch-asv",
                },
                "feature_identity": {
                    "type": "number",
                    "description": "OTU clustering identity threshold (0-1). Only used for OTU methods. Defaults to 0.97.",
                    "default": 0.97,
                },
                "chimera_mode": {
                    "type": "string",
                    "enum": ["ref", "none"],
                    "description": "Chimera removal mode: 'ref' uses VSEARCH uchime_ref; 'none' skips chimera removal. Defaults to 'ref'.",
                    "default": "ref",
                },
                "reference_db": {
                    "type": "string",
                    "description": "Path to the reference database FASTA for chimera removal. Defaults to 'databas/rdp_16s_v18.fa'.",
                    "default": "databas/rdp_16s_v18.fa",
                },
                "otutab_method": {
                    "type": "string",
                    "enum": ["usearch", "vsearch"],
                    "description": "Tool for OTU table generation. Defaults to 'usearch'.",
                    "default": "usearch",
                },
                "otutab_identity": {
                    "type": "number",
                    "description": "Identity threshold for OTU table mapping (0-1). Defaults to 0.97.",
                    "default": 0.97,
                },
                "annotation_database": {
                    "type": "string",
                    "enum": ["rdp_16s_v18", "silva_16s_v123"],
                    "description": "Reference database for VSEARCH SINTAX taxonomy annotation. Defaults to 'rdp_16s_v18'.",
                    "default": "rdp_16s_v18",
                },
                "sintax_cutoff": {
                    "type": "number",
                    "description": "Bootstrap confidence cutoff for SINTAX annotation (0-1). Defaults to 0.1.",
                    "default": 0.1,
                },
                "filter_route": {
                    "type": "string",
                    "enum": ["16s", "its", "none"],
                    "description": "Taxonomy filtering route: '16s' keeps Bacteria/Archaea; 'its' keeps Fungi; 'none' skips filtering. Defaults to '16s'.",
                    "default": "16s",
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of CPU threads for all steps. Defaults to 1.",
                    "default": 1,
                },
                "read1_suffix": {
                    "type": "string",
                    "description": "File suffix for forward reads. Defaults to '_1.fq.gz'.",
                    "default": "_1.fq.gz",
                },
                "read2_suffix": {
                    "type": "string",
                    "description": "File suffix for reverse reads. Defaults to '_2.fq.gz'.",
                    "default": "_2.fq.gz",
                },
                "usearch_path": {
                    "type": "string",
                    "description": "Explicit path to the USEARCH executable (optional).",
                },
                "vsearch_path": {
                    "type": "string",
                    "description": "Explicit path to the VSEARCH executable (optional).",
                },
                "rarefaction_depth": {
                    "type": "integer",
                    "description": "Rarefaction depth for alpha/beta diversity. Use 0 to auto-select minimum sample depth. Defaults to 0.",
                    "default": 0,
                },
                "rarefaction_seed": {
                    "type": "integer",
                    "description": "Random seed for rarefaction reproducibility. Defaults to 1.",
                    "default": 1,
                },
                "command_timeout": {
                    "type": "number",
                    "description": "Timeout in seconds for each external command call (optional).",
                },
                "params_source": {
                    "type": "string",
                    "description": "Path to the params YAML file used to launch this run, recorded in run_summary.json (optional).",
                },
            },
            "required": [
                "metadata_path",
                "seq_dir",
                "output_root",
                "fastq_stripleft",
                "fastq_stripright",
                "fastq_maxee_rate",
            ],
        },
        "fn": run_raw_amplicon_pipeline,
    },
]

_TOOL_DEFINITIONS.extend(_load_visualization_tool_definitions())
_TOOL_DEFINITIONS.extend(_load_skill_tool_definitions())

_SESSION_PIPELINE_DEFAULTS: dict[str, Any] = {}
_OPTIONAL_PIPELINE_PATH_ARGUMENTS = {
    "usearch_path",
    "vsearch_path",
    "beta_tree_path",
    "params_source",
}
_OPTIONAL_PIPELINE_UNSET_TEXTS = {"", "none", "null"}
_BETA_TREE_SKIP_TEXTS = {
    "-",
    ".",
    "./",
    ".\\",
    ",",
    "empty",
    "omit",
    "omitted",
    "skip",
    "skipped",
    "unset",
    "__skip_unifrac__",
    "_skip_unifrac_",
}

# ---------------------------------------------------------------------------
# Public registry API
# ---------------------------------------------------------------------------

def get_tool_schemas() -> list[dict[str, Any]]:
    """Return all tool definitions in OpenAI function-calling format.

    Returns:
        A list of dicts, each with keys ``name``, ``description``, and
        ``parameters`` (JSON Schema object). The ``fn`` key is stripped so
        the list is safe to serialise and send to an LLM.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in _TOOL_DEFINITIONS
    ]


def get_tool_map() -> dict[str, Callable[..., Any]]:
    """Return a mapping of tool name to callable.

    Returns:
        Dict keyed by tool name with the raw Python function as value.
    """
    return {tool["name"]: tool["fn"] for tool in _TOOL_DEFINITIONS}


def _normalize_optional_pipeline_path_argument(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value

    text = value.strip()
    unquoted_text = text.strip("\"'`").strip()
    lowered = unquoted_text.lower()
    if lowered in _OPTIONAL_PIPELINE_UNSET_TEXTS:
        return None

    if key == "beta_tree_path":
        basename = os.path.basename(unquoted_text).lower()
        if lowered in _BETA_TREE_SKIP_TEXTS or basename in _BETA_TREE_SKIP_TEXTS:
            return None
        if os.path.isdir(unquoted_text):
            return None

    return unquoted_text


def _normalize_optional_pipeline_timeout(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in _OPTIONAL_PIPELINE_UNSET_TEXTS:
            return None
        value = text

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return value

    if parsed <= 0:
        return None
    return value


def _normalize_pipeline_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(arguments)
    for key in _OPTIONAL_PIPELINE_PATH_ARGUMENTS:
        normalized[key] = _normalize_optional_pipeline_path_argument(
            key,
            normalized.get(key),
        )
    normalized["command_timeout"] = _normalize_optional_pipeline_timeout(
        normalized.get("command_timeout")
    )
    return normalized


def set_session_pipeline_defaults(defaults: dict[str, Any] | None) -> None:
    """Store session-scoped defaults for run_raw_amplicon_pipeline."""

    global _SESSION_PIPELINE_DEFAULTS
    _SESSION_PIPELINE_DEFAULTS = _normalize_pipeline_arguments(defaults or {})


def get_session_pipeline_defaults() -> dict[str, Any]:
    """Return the active session defaults for run_raw_amplicon_pipeline."""

    return dict(_SESSION_PIPELINE_DEFAULTS)


def _format_missing_path_error(tool_name: str, exc: FileNotFoundError) -> str:
    message = " ".join(str(exc).split())
    normalized = message.lower()

    if (
        "usearch executable not found" in normalized
        or "vsearch executable not found" in normalized
        or "unable to locate usearch" in normalized
        or "unable to locate vsearch" in normalized
    ):
        return (
            f"External executable not found while running '{tool_name}': {message}. "
            "Ensure USEARCH or VSEARCH is installed and accessible, or provide "
            "an explicit path via the 'usearch_path' / 'vsearch_path' argument."
        )

    if "metadata_path not found" in normalized:
        return (
            f"Input file not found while running '{tool_name}': {message}. "
            "Confirm 'metadata_path' in /params."
        )
    if "seq_dir not found" in normalized:
        return (
            f"Input directory not found while running '{tool_name}': {message}. "
            "Confirm 'seq_dir' in /params."
        )
    if "reference_db not found" in normalized:
        return (
            f"Reference database not found while running '{tool_name}': {message}. "
            "Confirm 'reference_db' in /params."
        )
    if "beta_tree_path not found" in normalized:
        return (
            f"Optional phylogenetic tree file not found while running '{tool_name}': {message}. "
            "Remove the external tree override to generate the tree automatically, or provide a valid tree file."
        )

    return (
        f"Input path not found while running '{tool_name}': {message}. "
        "Check the reported path in /params or in the current tool arguments."
    )


def _summarize_trace_value(value: Any, *, max_text: int = 500) -> Any:
    """Return a compact JSON-friendly representation for trace logs."""

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_text else value[: max_text - 3] + "..."
    if isinstance(value, (list, tuple)):
        items = [_summarize_trace_value(item, max_text=max_text) for item in value[:20]]
        if len(value) > 20:
            items.append(f"... {len(value) - 20} more items")
        return items
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 30:
                compact["..."] = f"{len(value) - 30} more keys"
                break
            compact[str(key)] = _summarize_trace_value(item, max_text=max_text)
        return compact

    text = repr(value)
    return text if len(text) <= max_text else text[: max_text - 3] + "..."


def _record_tool_trace(
    *,
    tool_name: str,
    raw_arguments: dict[str, Any],
    resolved_arguments: dict[str, Any] | None,
    result: dict[str, Any],
    start_time: float,
) -> None:
    """Write a best-effort trace event for a tool call."""

    try:
        from agent.skills.agent_tracing.tools import record_tool_trace_event
    except Exception:  # noqa: BLE001
        return

    duration_seconds = time.perf_counter() - start_time
    event = {
        "event_id": uuid.uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "status": result.get("status", "unknown"),
        "duration_seconds": round(duration_seconds, 6),
        "arguments": _summarize_trace_value(raw_arguments),
    }
    if resolved_arguments is not None and resolved_arguments != raw_arguments:
        event["resolved_arguments"] = _summarize_trace_value(resolved_arguments)
    if result.get("status") == "error":
        event["error"] = _summarize_trace_value(result.get("error"))

    try:
        record_tool_trace_event(event)
    except Exception:  # noqa: BLE001
        return


def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool by name and return a structured result.

    Catches all exceptions, including FileNotFoundError for missing
    executables, and returns them as ``{"status": "error", "error": ...}``
    so the agent loop can observe and report failures without crashing.

    Args:
        name: Tool name matching one of the registered definitions.
        arguments: Keyword arguments to pass to the tool function.

    Returns:
        A dict with key ``status`` set to ``"ok"`` or ``"error"``.
        On success, ``result`` holds the function's return value.
        On failure, ``error`` holds a human-readable message and
        ``traceback`` holds the full stack trace for debugging.
    """
    tool_map = get_tool_map()
    start_time = time.perf_counter()
    resolved_arguments_for_trace: dict[str, Any] | None = None

    if name not in tool_map:
        result = {
            "status": "error",
            "error": (
                f"Unknown tool '{name}'. "
                f"Available tools: {sorted(tool_map.keys())}"
            ),
        }
        _record_tool_trace(
            tool_name=name,
            raw_arguments=arguments,
            resolved_arguments=None,
            result=result,
            start_time=start_time,
        )
        return result

    fn = tool_map[name]
    try:
        resolved_arguments = dict(arguments)
        if name == "run_raw_amplicon_pipeline" and _SESSION_PIPELINE_DEFAULTS:
            merged_arguments = dict(_SESSION_PIPELINE_DEFAULTS)
            merged_arguments.update(resolved_arguments)
            resolved_arguments = merged_arguments
        if name == "run_raw_amplicon_pipeline":
            resolved_arguments = _normalize_pipeline_arguments(resolved_arguments)
        resolved_arguments_for_trace = dict(resolved_arguments)

        result = fn(**resolved_arguments)
        response = {"status": "ok", "result": result}
    except FileNotFoundError as exc:
        response = {
            "status": "error",
            "error": _format_missing_path_error(name, exc),
            "traceback": traceback.format_exc(),
        }
    except Exception as exc:  # noqa: BLE001
        response = {
            "status": "error",
            "error": f"Tool '{name}' raised {type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }

    _record_tool_trace(
        tool_name=name,
        raw_arguments=arguments,
        resolved_arguments=resolved_arguments_for_trace,
        result=response,
        start_time=start_time,
    )
    return response
