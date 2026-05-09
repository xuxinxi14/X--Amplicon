import { useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type { LLMConfigStatus, Locale, WebUISettings } from '../api/types';
import type { Messages } from '../i18n';
import { StatusBadge } from '../components/StatusBadge';

interface SettingsProps {
  settings: WebUISettings | null;
  messages: Messages;
  onSettingsSaved: (settings: WebUISettings) => void;
}

const plotFormats: WebUISettings['default_plot_format'][] = ['html', 'png', 'pdf', 'svg', 'all'];

function defaultSettings(locale: Locale): WebUISettings {
  return {
    language: locale,
    python_executable: null,
    default_output_root: 'work',
    default_metadata_path: 'metadata.txt',
    default_seq_dir: 'seq',
    default_group_col: 'Group',
    default_sample_id_col: 'SampleID',
    usearch_path: 'bin\\windows\\usearch.exe',
    vsearch_path: 'bin\\windows\\vsearch.exe',
    default_plot_format: 'all',
    authorized_dirs: []
  };
}

export function Settings({ settings, messages, onSettingsSaved }: SettingsProps) {
  const initial = useMemo(() => settings || defaultSettings('Chinese'), [settings]);
  const [form, setForm] = useState<WebUISettings>(initial);
  const [authorizedText, setAuthorizedText] = useState(initial.authorized_dirs.join('\n'));
  const [llmConfig, setLlmConfig] = useState<LLMConfigStatus | null>(null);
  const [llmModel, setLlmModel] = useState('');
  const [llmApiBase, setLlmApiBase] = useState('');
  const [llmApiKey, setLlmApiKey] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingLlm, setSavingLlm] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setForm(initial);
    setAuthorizedText(initial.authorized_dirs.join('\n'));
  }, [initial]);

  useEffect(() => {
    let cancelled = false;
    async function loadLlmConfig() {
      try {
        const loaded = await api.getLlmSettings();
        if (cancelled) {
          return;
        }
        setLlmConfig(loaded);
        setLlmModel(loaded.model);
        setLlmApiBase(loaded.api_base || '');
      } catch (err) {
        if (!cancelled) {
          setError(formatApiError(err));
        }
      }
    }
    void loadLlmConfig();
    return () => {
      cancelled = true;
    };
  }, []);

  function update<K extends keyof WebUISettings>(key: K, value: WebUISettings[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function saveSettings() {
    setSaving(true);
    setError(null);
    setNotice(null);
    const payload: WebUISettings = {
      ...form,
      authorized_dirs: authorizedText
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean)
    };
    try {
      const saved = await api.saveSettings(payload);
      onSettingsSaved(saved);
      setNotice(messages.saved);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveLlmSettings() {
    setSavingLlm(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await api.saveLlmSettings({
        model: llmModel,
        api_base: llmApiBase,
        api_key: llmApiKey || null,
        clear_api_key: clearApiKey
      });
      setLlmConfig(saved);
      setLlmModel(saved.model);
      setLlmApiBase(saved.api_base || '');
      setLlmApiKey('');
      setClearApiKey(false);
      setNotice(messages.settings.llmSaved);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSavingLlm(false);
    }
  }

  async function pickPath(kind: 'file' | 'directory', title: string, onPicked: (path: string) => void) {
    setSaving(true);
    setError(null);
    try {
      const result = await api.pickPath(kind, title);
      if (result.path) {
        onPicked(result.path);
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSaving(false);
    }
  }

  function addAuthorizedDir(path: string) {
    setAuthorizedText((current) => {
      const entries = current
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean);
      return entries.includes(path) ? current : [...entries, path].join('\n');
    });
  }

  const modelOptions = llmConfig?.models || [];
  const modelValues = new Set(modelOptions.map((model) => model.value));
  const modelChoice = modelValues.has(llmModel) ? llmModel : '__custom__';

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>{messages.settings.title}</h1>
          <p>{messages.settings.subtitle}</p>
        </div>
        <button className="primary-button" type="button" onClick={saveSettings} disabled={saving}>
          {saving ? messages.saving : messages.settings.saveSettings}
        </button>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <section className="panel settings-llm-panel">
        <div className="panel-header">
          <div>
            <h2>{messages.settings.llm}</h2>
            <p className="subtle-text">{messages.settings.llmSubtitle}</p>
          </div>
          <StatusBadge
            status={llmConfig?.api_key_configured ? 'passed' : 'warning'}
            label={llmConfig?.api_key_configured ? messages.settings.apiKeyConfigured : messages.settings.apiKeyMissing}
          />
        </div>
        <div className="summary-grid">
          <div><span>{messages.settings.currentModel}</span><strong>{llmConfig?.model || messages.notSet}</strong></div>
          <div><span>{messages.settings.provider}</span><strong>{llmConfig?.provider || messages.notSet}</strong></div>
          <div><span>{messages.settings.envFile}</span><code>{llmConfig?.env_file_path || messages.notSet}</code></div>
        </div>
        <div className="form-grid three-columns">
          <label className="field">
            <span>{messages.settings.modelSelect}</span>
            <select
              value={modelChoice}
              onChange={(event) => {
                if (event.target.value === '__custom__') {
                  setLlmModel(llmModel || llmConfig?.model || '');
                } else {
                  setLlmModel(event.target.value);
                }
              }}
            >
              {modelOptions.map((model) => (
                <option key={model.value} value={model.value}>{model.label}</option>
              ))}
              <option value="__custom__">{messages.settings.customModel}</option>
            </select>
          </label>
          <label className="field">
            <span>{messages.settings.customModel}</span>
            <input value={llmModel} onChange={(event) => setLlmModel(event.target.value)} />
            <small>{messages.settings.customModelHelp}</small>
          </label>
          <label className="field">
            <span>{messages.settings.apiBase}</span>
            <input value={llmApiBase} onChange={(event) => setLlmApiBase(event.target.value)} />
            <small>{messages.settings.apiBaseHelp}</small>
          </label>
          <label className="field wide-field">
            <span>{messages.settings.apiKey}</span>
            <input
              value={llmApiKey}
              onChange={(event) => setLlmApiKey(event.target.value)}
              placeholder={llmConfig?.api_key_configured ? messages.settings.apiKeyConfigured : messages.settings.apiKeyMissing}
              type="password"
              autoComplete="off"
            />
            <small>{messages.settings.apiKeyHelp}</small>
          </label>
          <label className="field checkbox-field">
            <input type="checkbox" checked={clearApiKey} onChange={(event) => setClearApiKey(event.target.checked)} />
            <span>{messages.settings.clearApiKey}</span>
            <small>{messages.settings.llmSecurity}</small>
          </label>
        </div>
        <div className="inline-actions">
          <button className="primary-button" type="button" onClick={saveLlmSettings} disabled={savingLlm || !llmModel.trim()}>
            {savingLlm ? messages.saving : messages.settings.saveLlm}
          </button>
        </div>
      </section>

      <div className="settings-grid">
        <section className="panel">
          <h2>{messages.settings.environment}</h2>
          <label className="field">
            <span>{messages.settings.language}</span>
            <select value={form.language} onChange={(event) => update('language', event.target.value as Locale)}>
              <option value="Chinese">{messages.chinese}</option>
              <option value="English">{messages.english}</option>
            </select>
          </label>
          <label className="field">
            <span>{messages.settings.pythonExecutable}</span>
            <input
              value={form.python_executable || ''}
              onChange={(event) => update('python_executable', event.target.value || null)}
              placeholder={messages.auto}
            />
          </label>
          <label className="field">
            <span>{messages.settings.usearchPath}</span>
            <input value={form.usearch_path} onChange={(event) => update('usearch_path', event.target.value)} />
          </label>
          <label className="field">
            <span>{messages.settings.vsearchPath}</span>
            <input value={form.vsearch_path} onChange={(event) => update('vsearch_path', event.target.value)} />
          </label>
        </section>

        <section className="panel">
          <h2>{messages.settings.defaults}</h2>
          <label className="field">
            <span>{messages.settings.outputRoot}</span>
            <div className="inline-input">
              <input
                value={form.default_output_root}
                onChange={(event) => update('default_output_root', event.target.value)}
              />
              <button
                type="button"
                onClick={() => void pickPath('directory', messages.settings.pickOutputRoot, (path) => update('default_output_root', path))}
              >
                {messages.settings.pickFolder}
              </button>
            </div>
          </label>
          <label className="field">
            <span>{messages.settings.metadataPath}</span>
            <div className="inline-input">
              <input
                value={form.default_metadata_path}
                onChange={(event) => update('default_metadata_path', event.target.value)}
              />
              <button
                type="button"
                onClick={() => void pickPath('file', messages.settings.pickMetadata, (path) => update('default_metadata_path', path))}
              >
                {messages.settings.pickFile}
              </button>
            </div>
          </label>
          <label className="field">
            <span>{messages.settings.seqDir}</span>
            <div className="inline-input">
              <input value={form.default_seq_dir} onChange={(event) => update('default_seq_dir', event.target.value)} />
              <button
                type="button"
                onClick={() => void pickPath('directory', messages.settings.pickSeqDir, (path) => update('default_seq_dir', path))}
              >
                {messages.settings.pickFolder}
              </button>
            </div>
          </label>
          <label className="field">
            <span>{messages.settings.sampleIdCol}</span>
            <input
              value={form.default_sample_id_col}
              onChange={(event) => update('default_sample_id_col', event.target.value)}
            />
          </label>
          <label className="field">
            <span>{messages.settings.groupCol}</span>
            <input value={form.default_group_col} onChange={(event) => update('default_group_col', event.target.value)} />
          </label>
        </section>

        <section className="panel">
          <h2>{messages.settings.visualization}</h2>
          <label className="field">
            <span>{messages.settings.plotFormat}</span>
            <select
              value={form.default_plot_format}
              onChange={(event) =>
                update('default_plot_format', event.target.value as WebUISettings['default_plot_format'])
              }
            >
              {plotFormats.map((format) => (
                <option key={format} value={format}>
                  {format}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{messages.settings.authorizedDirs}</span>
            <textarea value={authorizedText} onChange={(event) => setAuthorizedText(event.target.value)} rows={5} />
            <small>{messages.settings.authorizedDirsHelp}</small>
          </label>
          <div className="inline-actions">
            <button
              type="button"
              onClick={() => void pickPath('directory', messages.settings.pickAuthorizedDir, addAuthorizedDir)}
              disabled={saving}
            >
              {messages.settings.addAuthorizedDir}
            </button>
          </div>
        </section>
      </div>
    </section>
  );
}
