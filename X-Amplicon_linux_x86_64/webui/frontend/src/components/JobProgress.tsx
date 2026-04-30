import type { JobRecord, StatusKind } from '../api/types';
import type { Messages } from '../i18n';
import { StatusBadge } from './StatusBadge';

type ProgressStatus = StatusKind | 'pending' | 'unknown';

interface ProgressStep {
  key: string;
  label: string;
  status: ProgressStatus;
}

interface JobProgressProps {
  job: JobRecord | null;
  messages: Messages;
}

function statusText(status: string, messages: Messages): string {
  const labels = messages.runMonitor.statusLabels as Record<string, string>;
  return labels[status] || status;
}

function normalizeJobStatus(status: string): StatusKind {
  if (status === 'checking') {
    return 'running';
  }
  if (status === 'queued' || status === 'running' || status === 'completed' || status === 'failed' || status === 'cancelled') {
    return status;
  }
  return 'queued';
}

function pipelineStageStatus(job: JobRecord, index: number): ProgressStatus {
  if (job.status === 'completed') {
    return 'completed';
  }
  if (job.status === 'failed') {
    return index === 0 ? 'failed' : 'unknown';
  }
  if (job.status === 'cancelled') {
    return index === 0 ? 'cancelled' : 'unknown';
  }
  return 'unknown';
}

export function JobProgress({ job, messages }: JobProgressProps) {
  const labels = messages.runMonitor.progressSteps;

  if (!job) {
    return (
      <section className="panel">
        <h2>{messages.runMonitor.progress}</h2>
        <div className="empty-state compact">
          <p>{messages.runMonitor.selectJobFirst}</p>
        </div>
      </section>
    );
  }

  let steps: ProgressStep[];
  if (job.job_type === 'preflight') {
    steps = [
      { key: 'preflight', label: labels.preflight, status: normalizeJobStatus(job.status) },
      { key: 'inputCopy', label: labels.inputCopy, status: 'pending' },
      { key: 'mergeReads', label: labels.mergeReads, status: 'pending' },
      { key: 'qualityFilter', label: labels.qualityFilter, status: 'pending' },
      { key: 'dereplication', label: labels.dereplication, status: 'pending' },
      { key: 'featureGeneration', label: labels.featureGeneration, status: 'pending' },
      { key: 'taxonomy', label: labels.taxonomy, status: 'pending' },
      { key: 'rarefaction', label: labels.rarefaction, status: 'pending' },
      { key: 'diversity', label: labels.diversity, status: 'pending' },
      { key: 'visualization', label: labels.visualization, status: 'pending' },
      { key: 'report', label: labels.report, status: 'pending' }
    ];
  } else {
    const pipelineLabels = [
      labels.inputCopy,
      labels.mergeReads,
      labels.qualityFilter,
      labels.dereplication,
      labels.featureGeneration,
      labels.taxonomy,
      labels.rarefaction,
      labels.diversity,
      labels.visualization,
      labels.report
    ];
    steps = [
      { key: 'preflight', label: labels.preflight, status: 'pending' },
      ...pipelineLabels.map((label, index) => ({
        key: `${index}-${label}`,
        label,
        status: pipelineStageStatus(job, index)
      }))
    ];
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{messages.runMonitor.progress}</h2>
        <StatusBadge status={job.status} label={statusText(job.status, messages)} />
      </div>
      <p className="subtle-text">{messages.runMonitor.progressNote}</p>
      <ol className="progress-list">
        {steps.map((step) => (
          <li className={`progress-step progress-${step.status}`} key={step.key}>
            <span className="progress-dot" />
            <span>{step.label}</span>
            <StatusBadge status={step.status} label={messages.runMonitor.statusLabels[step.status]} />
          </li>
        ))}
      </ol>
    </section>
  );
}
