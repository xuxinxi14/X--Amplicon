import type {
  ApiErrorPayload,
  AgentChatPayload,
  AgentChatResponse,
  AgentExplainPayload,
  AgentExplainResponse,
  AgentStatusResponse,
  DatabaseCheckPayload,
  DatabaseRecord,
  DatabaseRegistrationPayload,
  FastqPairingPreview,
  FileListResponse,
  FilePickResponse,
  FileReadResponse,
  HealthResponse,
  JobLogsResponse,
  JobProgressResponse,
  JobRecord,
  LLMConfigStatus,
  LLMConfigUpdate,
  MetadataValidationResult,
  ParamsWriteResult,
  PipelineParamsDraft,
  ProjectCreatePayload,
  ProjectRecord,
  ProjectUpdatePayload,
  ResultIndex,
  TableExportFormat,
  WebUISettings
} from './types';

const viteApiBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
const isViteDev = window.location.port === '5173';
const defaultBase = isViteDev ? 'http://127.0.0.1:8765/api' : '/api';

export const API_BASE_URL = (viteApiBase || defaultBase).replace(/\/$/, '');

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== '') {
      search.set(key, String(value));
    }
  });
  return search.toString();
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {})
    },
    ...init
  });

  if (!response.ok) {
    let detail: unknown = undefined;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const payload: ApiErrorPayload = {
      status: response.status,
      message: response.statusText || 'Request failed',
      detail
    };
    throw payload;
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    let detail: unknown = undefined;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const payload: ApiErrorPayload = {
      status: response.status,
      message: response.statusText || 'Request failed',
      detail
    };
    throw payload;
  }

  return response.blob();
}

export const api = {
  baseUrl: API_BASE_URL,

  getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  getSettings(): Promise<WebUISettings> {
    return request<WebUISettings>('/settings');
  },

  saveSettings(settings: WebUISettings): Promise<WebUISettings> {
    return request<WebUISettings>('/settings', {
      method: 'PUT',
      body: JSON.stringify(settings)
    });
  },

  getLlmSettings(): Promise<LLMConfigStatus> {
    return request<LLMConfigStatus>('/settings/llm');
  },

  saveLlmSettings(payload: LLMConfigUpdate): Promise<LLMConfigStatus> {
    return request<LLMConfigStatus>('/settings/llm', {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  },

  listProjects(): Promise<ProjectRecord[]> {
    return request<ProjectRecord[]>('/projects');
  },

  createProject(payload: ProjectCreatePayload): Promise<ProjectRecord> {
    return request<ProjectRecord>('/projects', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  updateProject(projectId: string, payload: ProjectUpdatePayload): Promise<ProjectRecord> {
    return request<ProjectRecord>(`/projects/${encodeURIComponent(projectId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    });
  },

  validateMetadata(
    projectId: string,
    payload: { metadata_path?: string | null; sample_id_col: string; group_col: string }
  ): Promise<MetadataValidationResult> {
    return request<MetadataValidationResult>(`/projects/${encodeURIComponent(projectId)}/validate-metadata`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  previewPairs(
    projectId: string,
    payload: {
      metadata_path?: string | null;
      seq_dir?: string | null;
      sample_id_col: string;
      read1_suffix: string;
      read2_suffix: string;
    }
  ): Promise<FastqPairingPreview> {
    return request<FastqPairingPreview>(`/projects/${encodeURIComponent(projectId)}/preview-pairs`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  writeParams(projectId: string, payload: PipelineParamsDraft): Promise<ParamsWriteResult> {
    return request<ParamsWriteResult>(`/projects/${encodeURIComponent(projectId)}/write-params`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  startPreflight(projectId: string): Promise<JobRecord> {
    return request<JobRecord>(`/projects/${encodeURIComponent(projectId)}/preflight`, {
      method: 'POST'
    });
  },

  startRun(projectId: string): Promise<JobRecord> {
    return request<JobRecord>(`/projects/${encodeURIComponent(projectId)}/run`, {
      method: 'POST'
    });
  },

  listJobs(limit = 50): Promise<JobRecord[]> {
    return request<JobRecord[]>(`/jobs?limit=${limit}`);
  },

  getJob(jobId: string): Promise<JobRecord> {
    return request<JobRecord>(`/jobs/${encodeURIComponent(jobId)}`);
  },

  getJobLogs(jobId: string, tail = 80): Promise<JobLogsResponse> {
    return request<JobLogsResponse>(`/jobs/${encodeURIComponent(jobId)}/logs?tail=${tail}`);
  },

  getJobProgress(jobId: string): Promise<JobProgressResponse> {
    return request<JobProgressResponse>(`/jobs/${encodeURIComponent(jobId)}/progress`);
  },

  cancelJob(jobId: string): Promise<JobRecord> {
    return request<JobRecord>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST'
    });
  },

  getAgentStatus(): Promise<AgentStatusResponse> {
    return request<AgentStatusResponse>('/agent/status');
  },

  explainAgentIssue(payload: AgentExplainPayload): Promise<AgentExplainResponse> {
    return request<AgentExplainResponse>('/agent/explain', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  chatAgent(payload: AgentChatPayload): Promise<AgentChatResponse> {
    return request<AgentChatResponse>('/agent/chat', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  listDatabases(includeHash = false, registryPath?: string | null): Promise<DatabaseRecord[]> {
    return request<DatabaseRecord[]>(`/databases?${query({ include_hash: includeHash, registry_path: registryPath })}`);
  },

  checkDatabase(database: string, payload: DatabaseCheckPayload): Promise<DatabaseRecord> {
    return request<DatabaseRecord>(`/databases/${encodeURIComponent(database)}/check`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  registerDatabase(payload: DatabaseRegistrationPayload): Promise<DatabaseRecord> {
    return request<DatabaseRecord>('/databases', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getResults(projectId: string): Promise<ResultIndex> {
    return request<ResultIndex>(`/results/${encodeURIComponent(projectId)}`);
  },

  deleteProject(projectId: string): Promise<void> {
    return request<void>(`/projects/${encodeURIComponent(projectId)}`, {
      method: 'DELETE'
    });
  },

  clearProjects(): Promise<{ deleted: number; deleted_jobs: number }> {
    return request<{ deleted: number; deleted_jobs: number }>('/projects', {
      method: 'DELETE'
    });
  },

  startReport(projectId: string): Promise<JobRecord> {
    return request<JobRecord>(`/projects/${encodeURIComponent(projectId)}/report`, {
      method: 'POST'
    });
  },

  readFile(path: string, projectId?: string | null): Promise<FileReadResponse> {
    return request<FileReadResponse>(`/files/read?${query({ path, project_id: projectId })}`);
  },

  listFiles(path: string, projectId?: string | null): Promise<FileListResponse> {
    return request<FileListResponse>(`/files/list?${query({ path, project_id: projectId })}`);
  },

  pickPath(kind: 'file' | 'directory', title?: string): Promise<FilePickResponse> {
    return request<FilePickResponse>(`/files/pick?${query({ kind, title })}`);
  },

  fileViewUrl(path: string, projectId?: string | null): string {
    return `${API_BASE_URL}/files/view?${query({ path, project_id: projectId })}`;
  },

  fileDownloadUrl(path: string, projectId?: string | null): string {
    return `${API_BASE_URL}/files/download?${query({ path, project_id: projectId })}`;
  },

  exportTable(path: string, format: TableExportFormat, projectId?: string | null, maxRows?: number): Promise<Blob> {
    return requestBlob(`/files/table-export?${query({ path, format, project_id: projectId, max_rows: maxRows })}`);
  }
};

const zhErrorMap: Array<[RegExp, string]> = [
  [/Project name cannot be empty/i, '项目名称不能为空。'],
  [/Project not found/i, '未找到项目记录。'],
  [/metadata_path and seq_dir are required/i, '需要先选择 metadata 文件和 FASTQ 文件夹。'],
  [/metadata_path is required/i, '需要先选择 metadata 文件。'],
  [/seq_dir is required/i, '需要先选择 FASTQ 文件夹。'],
  [/Metadata file was not found/i, '未找到 metadata 文件。'],
  [/FASTQ directory was not found/i, '未找到 FASTQ 文件夹。'],
  [/File not found/i, '未找到文件。'],
  [/not previewable/i, '该文件类型不适合文本预览。'],
  [/too large to preview/i, '该文件过大，无法直接预览。'],
  [/Local file picker is not available/i, '当前环境不可用本地文件选择窗口。请确认 Web UI 后端运行在本机桌面会话中；远程服务器或无桌面环境请手动输入路径。'],
  [/Could not open local file picker/i, '无法打开本地文件选择窗口。远程服务器、无桌面会话或系统弹窗被拦截时，请手动输入路径。'],
  [/Table export format must be one of/i, '表格导出格式必须是 png、svg 或 pdf。'],
  [/Only TSV, CSV, or TXT tables can be exported/i, '只能导出 TSV、CSV 或 TXT 表格。'],
  [/Kaleido may be missing/i, '无法导出表格图片：可能缺少 kaleido，请安装或检查 plotly/kaleido 环境。'],
  [/Could not export table/i, '无法导出表格。请确认表格文件可读取，并检查 plotly/kaleido 环境。'],
  [/Path is outside authorized Web UI roots/i, '该路径不在 Web UI 授权访问目录内。请在设置中加入授权目录，或选择项目目录内的文件。'],
  [/Pipeline params written successfully/i, 'Pipeline 参数文件已写出。'],
  [/Metadata table is missing required columns/i, 'Metadata 表缺少必需列。'],
  [/Metadata table does not contain any sample rows/i, 'Metadata 表没有样本行。'],
  [/Metadata contains .* empty SampleID/i, 'Metadata 中存在空 SampleID。'],
  [/Metadata contains duplicate SampleID/i, 'Metadata 中存在重复 SampleID。'],
  [/Metadata contains .* empty group/i, 'Metadata 中存在空分组值。'],
  [/No non-empty group values were found/i, '没有找到非空分组值。'],
  [/Metadata is valid/i, 'Metadata 检查通过。'],
  [/Select a tab-delimited metadata table/i, '请选择制表符分隔的 metadata 表。'],
  [/Confirm the SampleID and Group column names/i, '请确认 SampleID 和 Group 列名，或在界面中选择正确列。'],
  [/Fix empty or duplicated SampleID values/i, '请先修复空 SampleID 或重复 SampleID。'],
  [/Group information is incomplete/i, '分组信息不完整，下游可视化或统计可能受限。'],
  [/Select a metadata table before previewing FASTQ pairs/i, '请先选择 metadata 表，再预览 FASTQ 配对。'],
  [/Select the folder that contains paired-end FASTQ files/i, '请选择包含双端 FASTQ 文件的文件夹。'],
  [/Validate metadata before previewing FASTQ pairs/i, '请先检查 metadata，再预览 FASTQ 配对。'],
  [/Check FASTQ file names or adjust Read1\/Read2 suffix settings/i, '请检查 FASTQ 文件名，或调整 Read1/Read2 后缀设置。'],
  [/Cannot clear history while jobs are running/i, '存在正在运行、检查或排队的任务。请先取消任务或等待任务结束后再清除历史。'],
  [/Preflight must complete successfully before starting full analysis/i, '启动完整分析前必须先完成并通过 preflight。'],
  [/Preflight record was not found/i, '未找到 preflight 记录。请重新运行 preflight。'],
  [/Request failed/i, '请求失败。'],
  [/Unknown API error/i, '未知 API 错误。']
];

function shouldUseChinese(): boolean {
  return document.documentElement.lang === 'zh-CN' || document.body.dataset.locale === 'Chinese';
}

function translateApiError(message: string): string {
  if (!shouldUseChinese()) {
    return message;
  }
  const matched = zhErrorMap.find(([pattern]) => pattern.test(message));
  return matched ? matched[1] : message;
}

export function formatApiError(error: unknown): string {
  if (typeof error === 'string') {
    return translateApiError(error);
  }
  if (error && typeof error === 'object') {
    const payload = error as ApiErrorPayload;
    if (payload.detail && typeof payload.detail === 'object' && 'detail' in payload.detail) {
      return translateApiError(String((payload.detail as { detail: unknown }).detail));
    }
    return translateApiError(payload.message || JSON.stringify(payload));
  }
  return translateApiError('Unknown API error');
}
