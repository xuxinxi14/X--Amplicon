import type { JobProgressResponse, JobRecord } from '../api/types';
import type { Messages } from '../i18n';
import { StatusBadge } from './StatusBadge';

interface JobProgressProps {
  job: JobRecord | null;
  progress: JobProgressResponse | null;
  messages: Messages;
}

function statusText(status: string, messages: Messages): string {
  const labels = messages.runMonitor.statusLabels as Record<string, string>;
  return labels[status] || status;
}

function stepLabel(key: string, messages: Messages): string {
  const labels = messages.runMonitor.progressSteps as Record<string, string>;
  return labels[key] || key;
}

function formatDuration(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return '';
  }
  return `${value.toFixed(value < 10 ? 1 : 0)}s`;
}

export function JobProgress({ job, progress, messages }: JobProgressProps) {
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

  const steps = progress?.steps || [];
  const completed = steps.filter((step) => step.status === 'completed').length;
  const progressSummary = messages.runMonitor.progressSummary
    .replace('{done}', String(completed))
    .replace('{total}', String(steps.length));

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{messages.runMonitor.progress}</h2>
        <StatusBadge status={progress?.status || job.status} label={statusText(progress?.status || job.status, messages)} />
      </div>
      <p className="subtle-text">{messages.runMonitor.progressNote}</p>
      {progress?.current_step ? <p className="subtle-text">{stepLabel(progress.current_step, messages)}</p> : null}
      {progress?.failed_step ? <div className="alert alert-error">{stepLabel(progress.failed_step, messages)}: {progress.message}</div> : null}
      {progress?.warnings?.map((warning, index) => (
        <div className="alert alert-warning" key={`${index}-${warning}`}>{warning}</div>
      ))}
      {progress ? <p className="subtle-text">{progressSummary}</p> : <p className="subtle-text">{messages.loading}</p>}
      <ol className="progress-list">
        {steps.map((step) => {
          const duration = formatDuration(step.duration_seconds);
          return (
            <li className={`progress-step progress-${step.status}`} key={`${step.source}-${step.key}`}>
              <span className="progress-dot" />
              <span className="progress-step-main">
                <strong>{stepLabel(step.key, messages)}</strong>
                {step.error ? <small className="error-text">{step.error}</small> : null}
                {!step.error && step.message ? <small>{step.message}</small> : null}
                {duration ? <small>{duration}</small> : null}
              </span>
              <StatusBadge status={step.status} label={statusText(step.status, messages)} />
            </li>
          );
        })}
      </ol>
    </section>
  );
}
