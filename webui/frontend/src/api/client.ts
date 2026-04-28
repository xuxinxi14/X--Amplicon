import type {
  ApiErrorPayload,
  AgentExplainPayload,
  AgentExplainResponse,
  AgentStatusResponse,
  DatabaseCheckPayload,
  DatabaseRecord,
  DatabaseRegistrationPayload,
  FastqPairingPreview,
  FileListResponse,
  FileReadResponse,
  HealthResponse,
  JobLogsResponse,
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

  fileViewUrl(path: string, projectId?: string | null): string {
    return `${API_BASE_URL}/files/view?${query({ path, project_id: projectId })}`;
  },

  fileDownloadUrl(path: string, projectId?: string | null): string {
    return `${API_BASE_URL}/files/download?${query({ path, project_id: projectId })}`;
  }
};

export function formatApiError(error: unknown): string {
  if (typeof error === 'string') {
    return error;
  }
  if (error && typeof error === 'object') {
    const payload = error as ApiErrorPayload;
    if (payload.detail && typeof payload.detail === 'object' && 'detail' in payload.detail) {
      return String((payload.detail as { detail: unknown }).detail);
    }
    return payload.message || JSON.stringify(payload);
  }
  return 'Unknown API error';
}
