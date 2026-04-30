import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type {
  AgentChatMessagePayload,
  AgentChatResponse,
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

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode?: AgentChatResponse['mode'];
  warnings?: string[];
  suggestedActions?: string[];
  suggestedCommands?: string[];
}

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

function compactProjectPath(value: string | null | undefined, messages: Messages): string {
  return value && value.trim() ? value : messages.notSet;
}

function toPayload(messages: ChatMessage[]): AgentChatMessagePayload[] {
  return messages
    .filter((message) => message.content.trim())
    .map((message) => ({ role: message.role, content: message.content }));
}

function messageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function Agent({ projects, locale, messages, onNavigate }: AgentProps) {
  const t = messages.agent.chat;
  const [status, setStatus] = useState<AgentStatusResponse | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || '');
  const [includeProjectContext, setIncludeProjectContext] = useState(true);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(() => [
    {
      id: 'welcome',
      role: 'assistant',
      content: t.welcome,
      suggestedActions: t.initialActions,
      suggestedCommands: []
    }
  ]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [chatMessages, sending]);

  useEffect(() => {
    setChatMessages((current) => {
      if (current.length !== 1 || current[0].id !== 'welcome') {
        return current;
      }
      return [{ ...current[0], content: t.welcome, suggestedActions: t.initialActions }];
    });
  }, [t.initialActions, t.welcome]);

  async function copyText(text: string) {
    await navigator.clipboard.writeText(text);
    setNotice(messages.agent.copied);
  }

  async function sendMessage(text = draft) {
    const content = text.trim();
    if (!content || sending) {
      return;
    }

    const userMessage: ChatMessage = { id: messageId(), role: 'user', content };
    const nextMessages = [...chatMessages, userMessage];
    setChatMessages(nextMessages);
    setDraft('');
    setNotice(null);
    setError(null);
    setSending(true);

    try {
      const response = await api.chatAgent({
        messages: toPayload(nextMessages),
        project_summary: includeProjectContext ? buildProjectSummary(selectedProject) : '',
        language: locale,
        prefer_llm: Boolean(status?.llm_available)
      });
      setChatMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: 'assistant',
          content: response.message,
          mode: response.mode,
          warnings: response.warnings,
          suggestedActions: response.suggested_actions,
          suggestedCommands: response.suggested_commands
        }
      ]);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSending(false);
    }
  }

  function startPrompt(prompt: string) {
    void sendMessage(prompt);
  }

  function resetChat() {
    setChatMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: t.welcome,
        suggestedActions: t.initialActions,
        suggestedCommands: []
      }
    ]);
    setDraft('');
    setNotice(null);
    setError(null);
  }

  function renderMessage(message: ChatMessage) {
    const isAssistant = message.role === 'assistant';
    return (
      <article className={`chat-message ${isAssistant ? 'assistant' : 'user'}`} key={message.id}>
        <div className="chat-avatar">{isAssistant ? 'AI' : 'U'}</div>
        <div className="chat-bubble">
          <div className="chat-message-meta">
            <strong>{isAssistant ? t.assistantName : t.userName}</strong>
            {message.mode ? <span>{message.mode === 'llm' ? messages.agent.llmMode : messages.agent.ruleMode}</span> : null}
          </div>
          <p>{message.content}</p>
          {message.warnings?.length ? (
            <div className="chat-warning">
              {message.warnings.map((warning) => <span key={warning}>{warning}</span>)}
            </div>
          ) : null}
          {message.suggestedActions?.length ? (
            <div className="chat-suggestions">
              {message.suggestedActions.map((action) => <span key={action}>{action}</span>)}
            </div>
          ) : null}
          {message.suggestedCommands?.length ? (
            <div className="chat-command-list">
              {message.suggestedCommands.map((command) => (
                <div className="chat-command-row" key={command}>
                  <code>{command}</code>
                  <button type="button" onClick={() => copyText(command)}>{messages.agent.copy}</button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </article>
    );
  }

  return (
    <section className="page agent-page">
      <div className="agent-hero agent-chat-hero">
        <div className="agent-hero-copy">
          <span className="eyebrow">{t.badge}</span>
          <h1>{t.headline}</h1>
          <p>{t.subtitle}</p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={() => onNavigate('newAnalysis')}>
              {messages.agent.guide.primaryAction}
            </button>
            <button type="button" onClick={() => onNavigate('runMonitor')}>
              {messages.nav.runMonitor}
            </button>
            <button type="button" onClick={() => onNavigate('results')}>
              {messages.nav.results}
            </button>
          </div>
        </div>
        <div className="agent-hero-panel agent-model-card">
          <div className="panel-header">
            <span className="muted-label">{messages.agent.status}</span>
            <StatusBadge status={status?.status || 'checking'} label={statusLabel(status, messages)} />
          </div>
          <div className="summary-grid compact-grid">
            <div><span>{messages.agent.model}</span><strong>{status?.model || 'NA'}</strong></div>
            <div><span>{messages.agent.provider}</span><strong>{status?.provider || 'NA'}</strong></div>
          </div>
          <p>{statusMessage(status, messages)}</p>
          <div className="inline-actions">
            <button type="button" onClick={loadStatus} disabled={loadingStatus}>
              {loadingStatus ? messages.loading : messages.refresh}
            </button>
            <button type="button" onClick={() => onNavigate('settings')}>{messages.nav.settings}</button>
          </div>
        </div>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <div className="agent-chat-layout">
        <section className="panel agent-chat-panel">
          <div className="agent-chat-toolbar">
            <div>
              <h2>{t.chatTitle}</h2>
              <p className="subtle-text">{t.chatSubtitle}</p>
            </div>
            <div className="inline-actions">
              <StatusBadge status={status?.llm_available ? 'online' : 'no-key'} label={status?.llm_available ? messages.agent.llmMode : messages.agent.ruleMode} />
              <button type="button" onClick={resetChat}>{t.reset}</button>
            </div>
          </div>

          <div className="quick-prompt-row agent-quick-prompts" aria-label={t.quickPromptsLabel}>
            {t.quickPrompts.map((prompt) => (
              <button key={prompt.label} type="button" onClick={() => startPrompt(prompt.prompt)} disabled={sending}>
                {prompt.label}
              </button>
            ))}
          </div>

          <div className="chat-thread" aria-live="polite">
            {chatMessages.map(renderMessage)}
            {sending ? (
              <article className="chat-message assistant">
                <div className="chat-avatar">AI</div>
                <div className="chat-bubble typing-bubble">
                  <div className="typing-dots"><span /><span /><span /></div>
                  <p>{t.thinking}</p>
                </div>
              </article>
            ) : null}
            <div ref={chatEndRef} />
          </div>

          <div className="chat-composer">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder={t.inputPlaceholder}
              rows={3}
            />
            <button className="primary-button" type="button" onClick={() => void sendMessage()} disabled={sending || !draft.trim()}>
              {sending ? t.sending : t.send}
            </button>
          </div>
        </section>

        <aside className="agent-context-rail">
          <section className="panel">
            <div className="panel-header">
              <h2>{t.contextTitle}</h2>
              <StatusBadge status={selectedProject ? 'passed' : 'pending'} label={selectedProject ? messages.newAnalysis.created : messages.runMonitor.statusLabels.pending} />
            </div>
            <label className="field">
              <span>{messages.agent.project}</span>
              <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}>
                <option value="">{messages.agent.noProject}</option>
                {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
            </label>
            <label className="checkbox-field inline-checkbox">
              <input
                type="checkbox"
                checked={includeProjectContext}
                onChange={(event) => setIncludeProjectContext(event.target.checked)}
              />
              <span>{t.includeProjectContext}</span>
            </label>
            {selectedProject ? (
              <div className="status-list agent-project-facts">
                <div className="status-row"><span>{messages.dashboard.project}</span><strong>{selectedProject.name}</strong></div>
                <div className="status-row"><span>{messages.dashboard.projectDir}</span><code>{selectedProject.project_dir}</code></div>
                <div className="status-row"><span>{messages.newAnalysis.metadataPath}</span><code>{compactProjectPath(selectedProject.metadata_path, messages)}</code></div>
                <div className="status-row"><span>{messages.newAnalysis.seqDir}</span><code>{compactProjectPath(selectedProject.seq_dir, messages)}</code></div>
                <div className="status-row"><span>{messages.newAnalysis.groupCol}</span><strong>{selectedProject.group_col}</strong></div>
              </div>
            ) : (
              <p className="subtle-text">{messages.agent.guide.noProjectHint}</p>
            )}
          </section>

          <section className="panel agent-step-panel">
            <h2>{t.workflowTitle}</h2>
            <ol className="agent-mini-steps">
              {messages.agent.guide.steps.map((step, index) => (
                <li key={step.title}>
                  <span>{index + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <p>{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="action-stack">
              <button type="button" onClick={() => onNavigate('newAnalysis')}>{messages.nav.newAnalysis}</button>
              <button type="button" onClick={() => onNavigate('runMonitor')}>{messages.nav.runMonitor}</button>
              <button type="button" onClick={() => onNavigate('results')}>{messages.nav.results}</button>
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
}
