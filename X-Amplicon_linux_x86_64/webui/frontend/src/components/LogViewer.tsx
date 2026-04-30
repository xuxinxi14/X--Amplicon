import { useState } from 'react';

import type { JobRecord } from '../api/types';
import type { Messages } from '../i18n';

interface LogViewerProps {
  job: JobRecord | null;
  logText: string;
  loading: boolean;
  messages: Messages;
  onRefreshLog: () => void;
  onCancelJob: () => void;
}

function canCancel(job: JobRecord | null): boolean {
  return Boolean(job && ['queued', 'checking', 'running'].includes(job.status));
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function LogViewer({ job, logText, loading, messages, onRefreshLog, onCancelJob }: LogViewerProps) {
  const [showTechnical, setShowTechnical] = useState(true);
  const [copied, setCopied] = useState(false);

  async function copyCommand() {
    if (!job?.display_command) {
      return;
    }
    try {
      await navigator.clipboard.writeText(job.display_command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  if (!job) {
    return (
      <section className="panel">
        <h2>{messages.runMonitor.logs}</h2>
        <div className="empty-state compact">
          <p>{messages.runMonitor.selectJobFirst}</p>
        </div>
      </section>
    );
  }

  const filename = `${job.id}.log`;
  const userStatus = job.error || job.message || messages.runMonitor.noStatusMessage;

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>{messages.runMonitor.logs}</h2>
          <p>{messages.runMonitor.logSubtitle}</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={onRefreshLog} disabled={loading}>
            {loading ? messages.loading : messages.runMonitor.refreshLog}
          </button>
          <button type="button" onClick={onCancelJob} disabled={!canCancel(job)}>
            {messages.runMonitor.cancelJob}
          </button>
        </div>
      </div>

      <section className="soft-panel">
        <h3>{messages.runMonitor.userStatus}</h3>
        <p>{userStatus}</p>
        {job.return_code !== null ? (
          <p className="subtle-text">
            {messages.runMonitor.returnCode}: <code>{job.return_code}</code>
          </p>
        ) : null}
      </section>

      <section className="soft-panel">
        <div className="log-toolbar">
          <h3>{messages.runMonitor.technicalLog}</h3>
          <div className="inline-actions">
            <button type="button" onClick={copyCommand} disabled={!job.display_command}>
              {copied ? messages.runMonitor.copied : messages.runMonitor.copyCommand}
            </button>
            <button type="button" onClick={() => downloadText(filename, logText || '')} disabled={!logText}>
              {messages.runMonitor.downloadLog}
            </button>
            <button type="button" onClick={() => setShowTechnical((current) => !current)}>
              {showTechnical ? messages.runMonitor.hideLog : messages.runMonitor.showLog}
            </button>
          </div>
        </div>
        <label className="field">
          <span>{messages.runMonitor.command}</span>
          <textarea value={job.display_command} readOnly rows={2} />
        </label>
        {showTechnical ? (
          <pre className={`log-preview${job.status === 'failed' ? ' failed-log' : ''}`}>
            {logText || messages.runMonitor.noLogYet}
          </pre>
        ) : null}
      </section>
    </section>
  );
}
