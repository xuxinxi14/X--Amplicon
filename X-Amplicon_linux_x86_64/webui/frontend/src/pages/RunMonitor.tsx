import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type { JobProgressResponse, JobRecord, ProjectRecord } from '../api/types';
import { JobProgress } from '../components/JobProgress';
import { LogViewer } from '../components/LogViewer';
import { StatusBadge } from '../components/StatusBadge';
import type { Messages } from '../i18n';
import type { PageId } from './pageTypes';

interface RunMonitorProps {
  projects: ProjectRecord[];
  messages: Messages;
  onNavigate: (page: PageId) => void;
}

function isActiveJob(job: JobRecord | null): boolean {
  return Boolean(job && ['queued', 'checking', 'running'].includes(job.status));
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return 'NA';
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function jobAgeText(job: JobRecord, messages: Messages): string {
  if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
    return `${messages.runMonitor.completedAt}: ${formatDate(job.completed_at)}`;
  }
  return `${messages.runMonitor.startedAt}: ${formatDate(job.started_at || job.created_at)}`;
}

function statusText(status: string, messages: Messages): string {
  const labels = messages.runMonitor.statusLabels as Record<string, string>;
  return labels[status] || status;
}

export function RunMonitor({ projects, messages, onNavigate }: RunMonitorProps) {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState('');
  const [selectedJob, setSelectedJob] = useState<JobRecord | null>(null);
  const [selectedProgress, setSelectedProgress] = useState<JobProgressResponse | null>(null);
  const [manualJobId, setManualJobId] = useState('');
  const [logText, setLogText] = useState('');
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [loadingLog, setLoadingLog] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const projectById = useMemo(() => {
    const mapping = new Map<string, ProjectRecord>();
    projects.forEach((project) => mapping.set(project.id, project));
    return mapping;
  }, [projects]);

  const refreshSelectedJob = useCallback(
    async (jobId = selectedJobId) => {
      if (!jobId) {
        setSelectedJob(null);
        setSelectedProgress(null);
        setLogText('');
        return;
      }
      try {
        const [job, logs, progress] = await Promise.all([
          api.getJob(jobId),
          api.getJobLogs(jobId, 100),
          api.getJobProgress(jobId)
        ]);
        setSelectedJob(job);
        setSelectedProgress(progress);
        setSelectedJobId(job.id);
        setManualJobId(job.id);
        setLogText(logs.text || '');
      } catch (err) {
        setError(formatApiError(err));
      }
    },
    [selectedJobId]
  );

  const loadJobs = useCallback(async () => {
    setLoadingJobs(true);
    setError(null);
    try {
      const loadedJobs = await api.listJobs(80);
      setJobs(loadedJobs);
      const selectedStillExists = Boolean(selectedJobId && loadedJobs.some((job) => job.id === selectedJobId));
      const nextSelectedId = selectedStillExists ? selectedJobId : loadedJobs[0]?.id || '';
      if (nextSelectedId) {
        setSelectedJobId(nextSelectedId);
        setManualJobId(nextSelectedId);
        await refreshSelectedJob(nextSelectedId);
      } else {
        setSelectedJobId('');
        setManualJobId('');
        setSelectedJob(null);
        setSelectedProgress(null);
        setLogText('');
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoadingJobs(false);
    }
  }, [refreshSelectedJob, selectedJobId]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!isActiveJob(selectedJob)) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshSelectedJob();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [refreshSelectedJob, selectedJob]);

  async function selectJob(jobId: string) {
    setSelectedJobId(jobId);
    setManualJobId(jobId);
    setNotice(null);
    setError(null);
    await refreshSelectedJob(jobId);
  }

  async function openManualJob() {
    const jobId = manualJobId.trim();
    if (!jobId) {
      return;
    }
    await selectJob(jobId);
  }

  async function refreshLog() {
    if (!selectedJob) {
      return;
    }
    setLoadingLog(true);
    setError(null);
    try {
      const logs = await api.getJobLogs(selectedJob.id, 120);
      setLogText(logs.text || '');
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoadingLog(false);
    }
  }

  async function cancelJob() {
    if (!selectedJob || !isActiveJob(selectedJob)) {
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const cancelled = await api.cancelJob(selectedJob.id);
      setSelectedJob(cancelled);
      setNotice(messages.runMonitor.cancelRequested);
      await refreshSelectedJob(cancelled.id);
      await loadJobs();
    } catch (err) {
      setError(formatApiError(err));
    }
  }

  const selectedProject = selectedJob?.project_id ? projectById.get(selectedJob.project_id) : null;

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>{messages.runMonitor.title}</h1>
          <p>{messages.runMonitor.subtitle}</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={loadJobs} disabled={loadingJobs}>
            {loadingJobs ? messages.loading : messages.refresh}
          </button>
          <button type="button" onClick={() => onNavigate('results')} disabled={!selectedJob || selectedJob.status !== 'completed'}>
            {messages.runMonitor.openResults}
          </button>
        </div>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <div className="section-grid two-columns">
        <section className="panel">
          <div className="panel-header">
            <h2>{messages.runMonitor.recentJobs}</h2>
            <span className="subtle-text">{jobs.length}</span>
          </div>
          <div className="field manual-job-field">
            <span>{messages.runMonitor.openByJobId}</span>
            <div className="inline-input">
              <input value={manualJobId} onChange={(event) => setManualJobId(event.target.value)} />
              <button type="button" onClick={openManualJob} disabled={!manualJobId.trim()}>
                {messages.open}
              </button>
            </div>
          </div>
          {jobs.length ? (
            <div className="job-list">
              {jobs.map((job) => (
                <button
                  type="button"
                  className={`job-list-item${selectedJob?.id === job.id ? ' active' : ''}`}
                  key={job.id}
                  onClick={() => void selectJob(job.id)}
                >
                  <span>
                    <strong>{job.job_type}</strong>
                    <span>{job.id}</span>
                    <small>{jobAgeText(job, messages)}</small>
                  </span>
                  <StatusBadge status={job.status} label={statusText(job.status, messages)} />
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-state compact">
              <p>{messages.runMonitor.noJobs}</p>
              <button className="primary-button" type="button" onClick={() => onNavigate('newAnalysis')}>
                {messages.nav.newAnalysis}
              </button>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{messages.runMonitor.jobDetails}</h2>
            {selectedJob ? <StatusBadge status={selectedJob.status} label={statusText(selectedJob.status, messages)} /> : null}
          </div>
          {selectedJob ? (
            <div className="summary-grid compact-grid">
              <div>
                <span>{messages.runMonitor.jobId}</span>
                <code>{selectedJob.id}</code>
              </div>
              <div>
                <span>{messages.runMonitor.jobType}</span>
                <strong>{selectedJob.job_type}</strong>
              </div>
              <div>
                <span>{messages.runMonitor.project}</span>
                <strong>{selectedProject?.name || selectedJob.project_id || 'NA'}</strong>
              </div>
              <div>
                <span>{messages.runMonitor.pid}</span>
                <code>{selectedJob.pid ?? 'NA'}</code>
              </div>
              <div>
                <span>{messages.runMonitor.cwd}</span>
                <code>{selectedJob.cwd}</code>
              </div>
              <div>
                <span>{messages.runMonitor.returnCode}</span>
                <code>{selectedJob.return_code ?? 'NA'}</code>
              </div>
            </div>
          ) : (
            <div className="empty-state compact">
              <p>{messages.runMonitor.selectJobFirst}</p>
            </div>
          )}
        </section>
      </div>

      <JobProgress job={selectedJob} progress={selectedProgress} messages={messages} />
      <LogViewer
        job={selectedJob}
        logText={logText}
        loading={loadingLog}
        messages={messages}
        onRefreshLog={refreshLog}
        onCancelJob={cancelJob}
      />
    </section>
  );
}
