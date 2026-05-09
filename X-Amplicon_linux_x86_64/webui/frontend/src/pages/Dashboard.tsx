import { useState } from 'react';

import { api, formatApiError } from '../api/client';
import type { DashboardData, ProjectRecord } from '../api/types';
import type { Messages } from '../i18n';
import type { PageId } from './pageTypes';
import { StatusBadge } from '../components/StatusBadge';

interface DashboardProps {
  data: DashboardData;
  loading: boolean;
  error: string | null;
  messages: Messages;
  onNavigate: (page: PageId) => void;
  onRefresh: () => void;
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return 'NA';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function ProjectRow({
  project,
  messages,
  onDelete
}: {
  project: ProjectRecord;
  messages: Messages;
  onDelete: (project: ProjectRecord) => void;
}) {
  return (
    <tr>
      <td>
        <strong>{project.name}</strong>
        <div className="table-subtext">{project.id}</div>
      </td>
      <td>{project.project_dir}</td>
      <td>{project.output_root}</td>
      <td>{formatDate(project.updated_at)}</td>
      <td>
        <button type="button" onClick={() => onDelete(project)}>
          {messages.dashboard.deleteHistory}
        </button>
      </td>
    </tr>
  );
}

export function Dashboard({ data, loading, error, messages, onNavigate, onRefresh }: DashboardProps) {
  const hasProjects = data.projects.length > 0;
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyBusy, setHistoryBusy] = useState(false);

  async function deleteHistory(project: ProjectRecord) {
    if (!window.confirm(messages.dashboard.deleteHistoryConfirm.replace('{name}', project.name))) {
      return;
    }
    setHistoryBusy(true);
    setHistoryError(null);
    try {
      await api.deleteProject(project.id);
      await onRefresh();
    } catch (err) {
      setHistoryError(formatApiError(err));
    } finally {
      setHistoryBusy(false);
    }
  }

  async function clearHistory() {
    if (!window.confirm(messages.dashboard.clearHistoryConfirm)) {
      return;
    }
    setHistoryBusy(true);
    setHistoryError(null);
    try {
      await api.clearProjects();
      await onRefresh();
    } catch (err) {
      setHistoryError(formatApiError(err));
    } finally {
      setHistoryBusy(false);
    }
  }

  return (
    <section className="page">
      <div className="agent-hero dashboard-hero">
        <div className="agent-hero-copy">
          <span className="eyebrow">{messages.dashboard.agentTitle}</span>
          <h1>{messages.dashboard.title}</h1>
          <p>{messages.dashboard.subtitle}</p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={() => onNavigate('agent')}>
              {messages.dashboard.askAgent}
            </button>
            <button type="button" onClick={() => onNavigate('newAnalysis')}>
              {messages.dashboard.guidedStart}
            </button>
            <button type="button" onClick={() => onNavigate('results')}>
              {messages.dashboard.reviewOutputs}
            </button>
          </div>
        </div>
        <div className="agent-hero-panel">
          <span className="muted-label">{messages.dashboard.workflowTitle}</span>
          <p>{messages.dashboard.workflowSubtitle}</p>
          <ol className="workflow-list">
            {messages.dashboard.workflowSteps.map((step, index) => (
              <li key={step.title}>
                <span>{index + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>

      {error ? <div className="alert alert-error">{error}</div> : null}
      {historyError ? <div className="alert alert-error">{historyError}</div> : null}

      <div className="section-grid two-columns">
        <section className="panel">
          <div className="panel-header">
            <h2>{messages.dashboard.environment}</h2>
            <button type="button" onClick={onRefresh}>{messages.refresh}</button>
          </div>
          <div className="status-list">
            <div className="status-row">
              <span>{messages.dashboard.backendStatus}</span>
              <StatusBadge
                status={data.health ? 'ok' : 'failed'}
                label={data.health ? messages.connected : messages.disconnected}
              />
            </div>
            <div className="status-row">
              <span>{messages.dashboard.currentPython}</span>
              <code>{data.health?.python || messages.notSet}</code>
            </div>
            <div className="status-row">
              <span>{messages.dashboard.projectRoot}</span>
              <code>{data.health?.cwd || messages.notSet}</code>
            </div>
            <div className="status-row">
              <span>{messages.apiBase}</span>
              <code>{api.baseUrl}</code>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{messages.dashboard.quickActions}</h2>
          </div>
          <div className="action-stack">
            <button className="primary-button" type="button" onClick={() => onNavigate('agent')}>{messages.nav.agent}</button>
            <button type="button" onClick={() => onNavigate('settings')}>{messages.nav.settings}</button>
            <button type="button" onClick={() => onNavigate('databases')}>{messages.nav.databases}</button>
            <button type="button" onClick={() => onNavigate('runMonitor')}>{messages.nav.runMonitor}</button>
          </div>
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <h2>{messages.dashboard.recentProjects}</h2>
          <div className="inline-actions">
            {loading || historyBusy ? <span className="subtle-text">{messages.loading}</span> : null}
            <button type="button" onClick={clearHistory} disabled={!hasProjects || historyBusy}>
              {messages.dashboard.clearHistory}
            </button>
          </div>
        </div>
        {hasProjects ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{messages.dashboard.project}</th>
                  <th>{messages.dashboard.projectDir}</th>
                  <th>{messages.dashboard.outputRoot}</th>
                  <th>{messages.dashboard.updatedAt}</th>
                  <th>{messages.dashboard.actions}</th>
                </tr>
              </thead>
              <tbody>
                {data.projects.slice(0, 6).map((project) => (
                  <ProjectRow key={project.id} project={project} messages={messages} onDelete={deleteHistory} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state compact">
            <p>{messages.dashboard.noProjects}</p>
            <button className="primary-button" type="button" onClick={() => onNavigate('newAnalysis')}>
              {messages.dashboard.newAnalysis}
            </button>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{messages.dashboard.recentResults}</h2>
        </div>
        <div className="result-shortcuts">
          <button type="button" onClick={() => onNavigate('results')}>{messages.results.tabs.alpha}</button>
          <button type="button" onClick={() => onNavigate('results')}>{messages.results.tabs.beta}</button>
          <button type="button" onClick={() => onNavigate('results')}>{messages.results.tabs.taxonomy}</button>
          <button type="button" onClick={() => onNavigate('results')}>{messages.results.tabs.differential}</button>
          <button type="button" onClick={() => onNavigate('results')}>{messages.results.tabs.report}</button>
        </div>
      </section>
    </section>
  );
}
