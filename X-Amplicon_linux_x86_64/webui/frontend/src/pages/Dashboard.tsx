import { api } from '../api/client';
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

function ProjectRow({ project, messages }: { project: ProjectRecord; messages: Messages }) {
  return (
    <tr>
      <td>
        <strong>{project.name}</strong>
        <div className="table-subtext">{project.id}</div>
      </td>
      <td>{project.project_dir}</td>
      <td>{project.output_root}</td>
      <td>{formatDate(project.updated_at)}</td>
    </tr>
  );
}

export function Dashboard({ data, loading, error, messages, onNavigate, onRefresh }: DashboardProps) {
  const hasProjects = data.projects.length > 0;

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
          {loading ? <span className="subtle-text">{messages.loading}</span> : null}
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
                </tr>
              </thead>
              <tbody>
                {data.projects.slice(0, 6).map((project) => (
                  <ProjectRow key={project.id} project={project} messages={messages} />
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
