import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type {
  AgentContextType,
  AgentExplainResponse,
  AgentStatusResponse,
  Locale,
  ProjectRecord
} from '../api/types';
import { StatusBadge } from '../components/StatusBadge';
import type { Messages } from '../i18n';
import type { PageId } from './pageTypes';

interface AgentProps {
  projects: ProjectRecord[];
  locale: Locale;
  messages: Messages;
  onNavigate: (page: PageId) => void;
}

const contextTypes: AgentContextType[] = [
  'general',
  'preflight',
  'metadata',
  'fastq',
  'database',
  'parameters',
  'results',
  'differential'
];

function statusLabel(status: AgentStatusResponse | null, messages: Messages): string {
  if (!status) {
    return messages.loading;
  }
  if (status.status === 'online') {
    return messages.agent.online;
  }
  if (status.status === 'offline') {
    return messages.agent.offline;
  }
  return messages.agent.noKey;
}

function statusMessage(status: AgentStatusResponse | null, messages: Messages): string {
  if (!status) {
    return messages.agent.statusLoading;
  }
  if (status.status === 'online') {
    return messages.agent.statusMessages.online;
  }
  if (status.status === 'offline') {
    return messages.agent.statusMessages.offline;
  }
  return messages.agent.statusMessages.noKey;
}

function statusText(status: string, messages: Messages): string {
  const labels = messages.runMonitor.statusLabels as Record<string, string>;
  return labels[status] || status;
}

function buildProjectSummary(project: ProjectRecord | null): string {
  if (!project) {
    return '';
  }
  return [
    `project_id=${project.id}`,
    `name=${project.name}`,
    `project_dir=${project.project_dir}`,
    `output_root=${project.output_root}`,
    `metadata_path=${project.metadata_path || ''}`,
    `seq_dir=${project.seq_dir || ''}`,
    `sample_id_col=${project.sample_id_col}`,
    `group_col=${project.group_col}`,
    `read1_suffix=${project.read1_suffix}`,
    `read2_suffix=${project.read2_suffix}`,
    `params_path=${project.params_path || ''}`,
    `last_job_id=${project.last_job_id || ''}`
  ].join('\n');
}

function guideTarget(index: number): PageId {
  return index >= 4 ? 'results' : 'newAnalysis';
}

export function Agent({ projects, locale, messages, onNavigate }: AgentProps) {
  const [status, setStatus] = useState<AgentStatusResponse | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || '');
  const [contextType, setContextType] = useState<AgentContextType>('preflight');
  const [question, setQuestion] = useState('');
  const [technicalText, setTechnicalText] = useState('');
  const [preferLlm, setPreferLlm] = useState(true);
  const [explanation, setExplanation] = useState<AgentExplainResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [explaining, setExplaining] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) || null,
    [projects, selectedProjectId]
  );

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true);
    setError(null);
    try {
      const loaded = await api.getAgentStatus();
      setStatus(loaded);
      setPreferLlm(loaded.llm_available);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!projects.find((project) => project.id === selectedProjectId)) {
      setSelectedProjectId(projects[0]?.id || '');
    }
  }, [projects, selectedProjectId]);

  async function copyText(text: string) {
    await navigator.clipboard.writeText(text);
    setNotice(messages.agent.copied);
  }

  async function explain() {
    setExplaining(true);
    setError(null);
    setNotice(null);
    setExplanation(null);
    try {
      const result = await api.explainAgentIssue({
        question,
        technical_text: technicalText,
        context_type: contextType,
        project_summary: buildProjectSummary(selectedProject),
        language: locale,
        prefer_llm: preferLlm && Boolean(status?.llm_available)
      });
      setExplanation(result);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setExplaining(false);
    }
  }

  function fillExample(kind: AgentContextType) {
    setContextType(kind);
    const example = messages.agent.examples[kind] || messages.agent.examples.general;
    setQuestion(example.question);
    setTechnicalText(example.technicalText);
  }

  function renderStartGuide() {
    return (
      <div className="agent-guide-layout">
        <section className="panel agent-guide-main">
          <div className="panel-header">
            <div>
              <span className="eyebrow">{messages.agent.guide.nextRecommended}</span>
              <h2>{messages.agent.guide.primaryAction}</h2>
              <p className="subtle-text">{messages.agent.guide.body}</p>
            </div>
            <button className="primary-button" type="button" onClick={() => onNavigate('newAnalysis')}>
              {messages.agent.guide.primaryAction}
            </button>
          </div>
          <div className="agent-guide-steps">
            {messages.agent.guide.steps.map((step, index) => (
              <article className="agent-guide-step" key={step.title}>
                <div className="agent-guide-step-number">{index + 1}</div>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                  <button type="button" onClick={() => onNavigate(guideTarget(index))}>
                    {step.cta}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="agent-guide-side">
          <section className="panel">
            <div className="panel-header">
              <h2>{messages.agent.guide.currentProject}</h2>
              <StatusBadge status={selectedProject ? 'passed' : 'pending'} label={selectedProject ? messages.newAnalysis.created : messages.runMonitor.statusLabels.pending} />
            </div>
            {selectedProject ? (
              <div className="status-list">
                <div className="status-row">
                  <span>{messages.dashboard.project}</span>
                  <strong>{selectedProject.name}</strong>
                </div>
                <div className="status-row">
                  <span>{messages.dashboard.projectDir}</span>
                  <code>{selectedProject.project_dir}</code>
                </div>
                <div className="status-row">
                  <span>{messages.newAnalysis.metadataPath}</span>
                  <code>{selectedProject.metadata_path || messages.notSet}</code>
                </div>
              </div>
            ) : (
              <p className="subtle-text">{messages.agent.guide.noProjectHint}</p>
            )}
          </section>

          <section className="panel agent-checklist-panel">
            <h2>{messages.agent.guide.checklistTitle}</h2>
            <ul className="agent-checklist">
              {messages.agent.guide.checklist.map((item) => (
                <li key={item}>
                  <span aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
    );
  }

  function renderStatus() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.agent.status}</h2>
          <StatusBadge status={status?.status || 'checking'} label={statusLabel(status, messages)} />
        </div>
        <div className="summary-grid compact-grid">
          <div><span>{messages.agent.model}</span><strong>{status?.model || 'NA'}</strong></div>
          <div><span>{messages.agent.provider}</span><strong>{status?.provider || 'NA'}</strong></div>
          <div><span>{messages.agent.apiBase}</span><strong>{status?.api_base_configured ? messages.saved : messages.notSet}</strong></div>
          <div><span>{messages.agent.key}</span><strong>{status?.key_configured ? messages.saved : messages.notSet}</strong></div>
        </div>
        <p className="subtle-text">{statusMessage(status, messages)}</p>
        {status?.disabled_reason ? <div className="warning-block"><strong>{messages.agent.disabledReason}</strong><p>{status.disabled_reason}</p></div> : null}
        <div className="tag-list">
          {(status?.capabilities || []).map((capability) => <span className="tag" key={capability}>{capability}</span>)}
        </div>
        <div className="inline-actions agent-status-actions">
          <button type="button" onClick={loadStatus} disabled={loadingStatus}>{loadingStatus ? messages.loading : messages.refresh}</button>
          <button type="button" onClick={() => onNavigate('settings')}>{messages.nav.settings}</button>
        </div>
      </section>
    );
  }

  function renderExplainer() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.agent.explainer}</h2>
          <StatusBadge status={preferLlm && status?.llm_available ? 'online' : 'no-key'} label={preferLlm && status?.llm_available ? messages.agent.llmMode : messages.agent.ruleMode} />
        </div>
        <div className="form-grid two-columns">
          <label className="field">
            <span>{messages.agent.project}</span>
            <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}>
              <option value="">{messages.agent.noProject}</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>{messages.agent.context}</span>
            <select value={contextType} onChange={(event) => setContextType(event.target.value as AgentContextType)}>
              {contextTypes.map((item) => <option key={item} value={item}>{messages.agent.contextLabels[item]}</option>)}
            </select>
          </label>
        </div>
        <label className="field">
          <span>{messages.agent.question}</span>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={messages.agent.questionPlaceholder} />
        </label>
        <div className="quick-prompt-row" aria-label={messages.agent.commonHelp}>
          {contextTypes.filter((item) => item !== 'general').map((item) => (
            <button key={item} type="button" onClick={() => fillExample(item)}>
              {messages.agent.contextLabels[item]}
            </button>
          ))}
        </div>
        <label className="field">
          <span>{messages.agent.technicalText}</span>
          <textarea value={technicalText} onChange={(event) => setTechnicalText(event.target.value)} placeholder={messages.agent.technicalPlaceholder} />
        </label>
        <div className="inline-actions">
          <label className="checkbox-field inline-checkbox">
            <input type="checkbox" checked={preferLlm} disabled={!status?.llm_available} onChange={(event) => setPreferLlm(event.target.checked)} />
            <span>{messages.agent.preferLlm}</span>
          </label>
          <button className="primary-button" type="button" onClick={explain} disabled={explaining || (!question.trim() && !technicalText.trim())}>
            {explaining ? messages.agent.explaining : messages.agent.explain}
          </button>
        </div>
      </section>
    );
  }

  function renderExplanation() {
    if (!explanation) {
      return null;
    }
    return (
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{explanation.title}</h2>
            <p className="subtle-text">{messages.agent.mode}: {explanation.mode}</p>
          </div>
          <StatusBadge status={explanation.status} label={statusText(explanation.status, messages)} />
        </div>
        <p>{explanation.summary}</p>
        {explanation.warnings.length ? (
          <div className="warning-block">
            <strong>{messages.agent.warnings}</strong>
            {explanation.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        ) : null}
        <div className="section-grid two-columns">
          <div className="soft-panel">
            <h3>{messages.agent.likelyCauses}</h3>
            <ul className="message-list">
              {explanation.likely_causes.map((cause) => <li key={cause}>{cause}</li>)}
            </ul>
          </div>
          <div className="soft-panel">
            <h3>{messages.agent.recoverySteps}</h3>
            <ul className="message-list">
              {explanation.recovery_steps.map((step) => <li key={step}>{step}</li>)}
            </ul>
          </div>
        </div>
        {explanation.commands.length ? (
          <section className="soft-panel">
            <h3>{messages.agent.suggestedCommands}</h3>
            <div className="command-list">
              {explanation.commands.map((command) => (
                <div className="command-row" key={command}>
                  <code>{command}</code>
                  <button type="button" onClick={() => copyText(command)}>{messages.agent.copy}</button>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </section>
    );
  }

  return (
    <section className="page">
      <div className="agent-hero agent-start-hero">
        <div className="agent-hero-copy">
          <span className="eyebrow">{messages.agent.guide.badge}</span>
          <h1>{messages.agent.guide.headline}</h1>
          <p>{messages.agent.guide.body}</p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={() => onNavigate('newAnalysis')}>
              {messages.agent.guide.primaryAction}
            </button>
            <button type="button" onClick={() => onNavigate('results')}>
              {messages.agent.guide.secondaryAction}
            </button>
          </div>
        </div>
        <div className="agent-hero-panel">
          <span className="muted-label">{messages.agent.guide.statusReady}</span>
          <div className="hero-status-line">
            <StatusBadge status={status?.status || 'checking'} label={statusLabel(status, messages)} />
            <strong>{status?.model || 'NA'}</strong>
          </div>
          <p>{statusMessage(status, messages)}</p>
          <div className="tag-list">
            {(status?.capabilities || []).slice(0, 4).map((capability) => (
              <span className="tag" key={capability}>{capability}</span>
            ))}
          </div>
        </div>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      {renderStartGuide()}

      {renderExplanation()}

      <section className="agent-secondary-tool">
        <div className="panel-header">
          <div>
            <h2>{messages.agent.guide.troubleshootingTitle}</h2>
            <p className="subtle-text">{messages.agent.guide.troubleshootingBody}</p>
          </div>
          <button type="button" onClick={() => fillExample('metadata')}>{messages.agent.useInExplainer}</button>
        </div>
        <div className="agent-workspace">
          {renderExplainer()}
          {renderStatus()}
        </div>
      </section>
    </section>
  );
}
