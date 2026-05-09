"""Core workflows for sequence_processor."""

from .usearch_ASV_unoise3 import (
    load_usearch_asv_defaults,
    run_usearch_unoise3_denoising,
)
from .usearch_otu_cluster import (
    load_usearch_otu_defaults,
    run_usearch_otu_clustering,
)
from .otu_table_generator import (
    load_otutab_defaults,
    run_otutab_generation,
)
from .otutab_filter import (
    run_otutab_filter,
)
from .otutab_rare import (
    run_otutab_rare,
)
from .alpha_diversity import (
    calculate_alpha_diversity,
    calculate_rarefaction_curve,
)
from .beta_diversity import (
    calculate_beta_distance,
)
from .database_registry import (
    check_database,
    list_databases,
    register_database,
    resolve_database_record,
)
from .feature_filter import (
    calculate_group_abundance,
)
from .raw_amplicon_pipeline import (
    run_raw_amplicon_pipeline,
)
from .report_generator import (
    generate_analysis_report,
)
from .taxonomy_summary import (
    parse_sintax_to_dataframe,
    summarize_taxa_abundance,
)
from .stat_taxonomy import (
    build_differential_comparison_plan,
    plot_differential_heatmap,
    plot_differential_volcano,
    run_taxonomy_differential_abundance,
)
from .vsearch_uchime_ref import (
    load_vsearch_uchime_ref_defaults,
    run_vsearch_uchime_ref,
)
from .vsearch_sintax import (
    load_vsearch_sintax_defaults,
    resolve_sintax_database_path,
    run_vsearch_sintax,
)
from .vsearch_otu_cluster import (
    load_vsearch_otu_defaults,
    run_vsearch_clustering,
    run_vsearch_otu_clustering,
)

__all__ = [
    "load_vsearch_otu_defaults",
    "run_vsearch_clustering",
    "run_vsearch_otu_clustering",
    "load_vsearch_uchime_ref_defaults",
    "run_vsearch_uchime_ref",
    "load_vsearch_sintax_defaults",
    "resolve_sintax_database_path",
    "run_vsearch_sintax",
    "load_otutab_defaults",
    "run_otutab_generation",
    "run_otutab_filter",
    "run_otutab_rare",
    "calculate_alpha_diversity",
    "calculate_rarefaction_curve",
    "calculate_group_abundance",
    "calculate_beta_distance",
    "list_databases",
    "check_database",
    "register_database",
    "resolve_database_record",
    "parse_sintax_to_dataframe",
    "summarize_taxa_abundance",
    "build_differential_comparison_plan",
    "run_taxonomy_differential_abundance",
    "plot_differential_volcano",
    "plot_differential_heatmap",
    "run_raw_amplicon_pipeline",
    "generate_analysis_report",
    "load_usearch_otu_defaults",
    "run_usearch_otu_clustering",
    "load_usearch_asv_defaults",
    "run_usearch_unoise3_denoising",
]
