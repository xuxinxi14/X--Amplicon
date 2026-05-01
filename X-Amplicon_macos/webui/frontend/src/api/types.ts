export type Locale = 'Chinese' | 'English';

export type StatusKind =
  | 'ok'
  | 'warning'
  | 'failed'
  | 'passed'
  | 'checking'
  | 'running'
  | 'completed'
  | 'queued'
  | 'cancelled';

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  cwd: string;
  python: string;
  time: string;
}

export interface WebUISettings {
  language: Locale;
  python_executable: string | null;
  default_output_root: string;
  default_metadata_path: string;
  default_seq_dir: string;
  default_group_col: string;
  default_sample_id_col: string;
  usearch_path: string;
  vsearch_path: string;
  default_plot_format: 'html' | 'png' | 'pdf' | 'svg' | 'all';
  authorized_dirs: string[];
}

export interface LLMModelOption {
  value: string;
  label: string;
}

export interface LLMConfigStatus {
  model: string;
  api_base: string;
  api_base_configured: boolean;
  api_key_configured: boolean;
  provider: string;
  env_file_path: string;
  models: LLMModelOption[];
}

export interface LLMConfigUpdate {
  model?: string | null;
  api_base?: string | null;
  api_key?: string | null;
  clear_api_key?: boolean;
}

export interface ProjectRecord {
  id: string;
  name: string;
  project_dir: string;
  output_root: string;
  analysis_type: string;
  metadata_path: string | null;
  seq_dir: string | null;
  sample_id_col: string;
  group_col: string;
  read1_suffix: string;
  read2_suffix: string;
  params_path: string | null;
  last_job_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreatePayload {
  name: string;
  project_dir?: string | null;
  output_root: string;
  analysis_type: string;
}

export interface ProjectUpdatePayload {
  name?: string | null;
  project_dir?: string | null;
  output_root?: string | null;
  analysis_type?: string | null;
  metadata_path?: string | null;
  seq_dir?: string | null;
  sample_id_col?: string | null;
  group_col?: string | null;
  read1_suffix?: string | null;
  read2_suffix?: string | null;
  params_path?: string | null;
  last_job_id?: string | null;
}

export interface GroupSummary {
  group: string;
  count: number;
  samples: string[];
}

export interface MetadataValidationResult {
  status: 'passed' | 'warning' | 'failed';
  metadata_path: string;
  exists: boolean;
  readable: boolean;
  rows: number;
  columns: number;
  column_names: string[];
  sample_id_col: string;
  group_col: string;
  sample_count: number;
  groups: GroupSummary[];
  missing_columns: string[];
  duplicate_sample_ids: string[];
  empty_sample_ids: number;
  empty_group_values: number;
  messages: string[];
  suggestions: string[];
}

export interface FastqPairRecord {
  sample_id: string;
  read1_path: string;
  read2_path: string;
  read1_exists: boolean;
  read2_exists: boolean;
  status: 'ok' | 'missing_r1' | 'missing_r2' | 'missing_both';
}

export interface FastqPairingPreview {
  status: 'passed' | 'warning' | 'failed';
  metadata_path: string;
  seq_dir: string;
  read1_suffix: string;
  read2_suffix: string;
  sample_count: number;
  matched_pairs: number;
  missing_read1: string[];
  missing_read2: string[];
  extra_fastq_files: string[];
  pairs: FastqPairRecord[];
  messages: string[];
  suggestions: string[];
}

export interface PipelineParamsDraft {
  metadata_path?: string | null;
  seq_dir?: string | null;
  output_root?: string;
  read1_suffix?: string;
  read2_suffix?: string;
  fastq_stripleft?: number;
  fastq_stripright?: number;
  fastq_maxee_rate?: number;
  feature_method?: 'usearch-asv' | 'usearch-otu' | 'vsearch-otu';
  feature_minsize?: number;
  feature_identity?: number;
  chimera_mode?: 'ref' | 'none';
  reference_db?: string;
  otutab_method?: 'usearch' | 'vsearch';
  otutab_identity?: number;
  annotation_database?: string;
  sintax_cutoff?: number;
  filter_route?: '16s' | 'its' | 'none';
  beta_tree_path?: string | null;
  rarefaction_depth?: number;
  rarefaction_seed?: number;
  threads?: number;
  usearch_path?: string | null;
  vsearch_path?: string | null;
  command_timeout?: number | null;
  color_palette?: string | null;
  differential?: Record<string, unknown>;
}

export interface ParamsWriteResult {
  status: 'passed' | 'failed';
  params_path: string;
  project_id: string;
  message: string;
  run_pipeline: Record<string, unknown>;
}

export interface JobRecord {
  id: string;
  project_id: string | null;
  job_type: string;
  status: string;
  display_command: string;
  cwd: string;
  pid: number | null;
  return_code: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  log_path: string;
  event_path: string;
  message: string;
  error: string | null;
}

export interface JobLogsResponse {
  job_id: string;
  log_path: string;
  text: string;
}

export interface DatabaseRecord {
  name: string;
  version?: string | null;
  taxonomy_format?: string;
  type?: string;
  database_type?: string;
  roles?: string[];
  sequence_path?: string;
  path?: string;
  aliases?: string[];
  source?: string;
  registry_path?: string;
  expected_sha256?: string;
  sha256?: string;
  sha256_error?: string;
  hash_matches?: boolean;
  status?: string;
  message?: string;
  query?: string;
  description?: string;
  url?: string;
  citation?: string;
  error?: string;
  exists?: boolean;
  is_file?: boolean;
  is_dir?: boolean;
  size_bytes?: number;
  modified_at?: string;
}

export interface DatabaseCheckPayload {
  include_hash?: boolean;
  registry_path?: string | null;
}

export interface DatabaseRegistrationPayload {
  name: string;
  path: string;
  version?: string | null;
  taxonomy_format?: string;
  database_type?: string;
  registry_path?: string | null;
  aliases?: string[];
  roles?: string[];
  sha256?: string | null;
  compute_hash?: boolean;
  allow_missing?: boolean;
  overwrite?: boolean;
}

export interface AgentStatusResponse {
  status: 'online' | 'offline' | 'no-key';
  llm_available: boolean;
  key_configured: boolean;
  model: string;
  api_base_configured: boolean;
  provider: string;
  message: string;
  capabilities: string[];
  disabled_reason?: string | null;
}

export type AgentContextType =
  | 'general'
  | 'preflight'
  | 'metadata'
  | 'fastq'
  | 'database'
  | 'parameters'
  | 'results'
  | 'differential';

export interface AgentExplainPayload {
  question: string;
  technical_text: string;
  context_type: AgentContextType;
  project_summary?: string;
  language: Locale;
  prefer_llm: boolean;
}

export interface AgentExplainResponse {
  status: 'ok' | 'warning' | 'failed';
  mode: 'rule_based' | 'llm' | 'fallback';
  title: string;
  summary: string;
  likely_causes: string[];
  recovery_steps: string[];
  commands: string[];
  warnings: string[];
  raw_response?: string | null;
}

export interface AgentChatMessagePayload {
  role: 'user' | 'assistant';
  content: string;
}

export interface AgentChatPayload {
  messages: AgentChatMessagePayload[];
  project_summary?: string;
  language: Locale;
  prefer_llm: boolean;
}

export interface AgentChatResponse {
  status: 'ok' | 'warning' | 'failed';
  mode: 'rule_based' | 'llm' | 'fallback';
  message: string;
  suggested_actions: string[];
  suggested_commands: string[];
  warnings: string[];
}

export interface ResultFigure {
  label: string;
  path: string;
  category: string;
}

export interface DifferentialComparisonResult {
  comparison: string;
  result_path: string | null;
  significant_path: string | null;
  tested_features: number | null;
  significant_features: number | null;
  volcano: string | null;
  heatmap: string | null;
}

export interface ResultIndex {
  project_id: string;
  final_dir: string;
  available: boolean;
  messages: string[];
  summary_path: string | null;
  provenance_json: string | null;
  provenance_markdown: string | null;
  plots_index: string | null;
  report_html: string | null;
  report_markdown: string | null;
  report_data: string | null;
  figures: Record<string, ResultFigure[]>;
  differential: DifferentialComparisonResult[];
  files: Record<string, string | null>;
}

export interface FileReadResponse {
  path: string;
  name: string;
  size: number;
  text: string;
}

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified: number;
}

export interface FileListResponse {
  path: string;
  entries: FileEntry[];
}

export interface ApiErrorPayload {
  status: number;
  message: string;
  detail?: unknown;
}

export interface DashboardData {
  health: HealthResponse | null;
  settings: WebUISettings | null;
  projects: ProjectRecord[];
}
