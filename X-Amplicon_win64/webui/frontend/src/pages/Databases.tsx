import { useEffect, useMemo, useState } from 'react';
import type { FormEvent } from 'react';

import { api, formatApiError } from '../api/client';
import type { DatabaseRecord, DatabaseRegistrationPayload } from '../api/types';
import { StatusBadge } from '../components/StatusBadge';
import type { Messages } from '../i18n';

interface DatabaseFormState {
  name: string;
  path: string;
  version: string;
  taxonomyFormat: string;
  databaseType: string;
  aliases: string;
  roles: string;
  sha256: string;
  computeHash: boolean;
  allowMissing: boolean;
  overwrite: boolean;
}

const defaultForm: DatabaseFormState = {
  name: '',
  path: '',
  version: '',
  taxonomyFormat: 'sintax',
  databaseType: 'taxonomy_annotation',
  aliases: '',
  roles: 'taxonomy_annotation',
  sha256: '',
  computeHash: false,
  allowMissing: false,
  overwrite: false
};

function formatBytes(size: number | undefined): string {
  if (typeof size !== 'number') {
    return 'NA';
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  if (size < 1024 * 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function formatDate(value: string | undefined): string {
  if (!value) {
    return 'NA';
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function splitList(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function optionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function databaseStatus(record: DatabaseRecord, messages: Messages): { status: string; label: string } {
  const statusLabels = messages.runMonitor.statusLabels as Record<string, string>;
  if (record.status) {
    return { status: record.status, label: statusLabels[record.status] || record.status };
  }
  if (record.exists === true) {
    return { status: 'passed', label: messages.databases.available };
  }
  if (record.exists === false) {
    return { status: 'failed', label: messages.databases.missing };
  }
  return { status: 'unknown', label: statusLabels.unknown || 'unknown' };
}

function pathForDisplay(record: DatabaseRecord): string {
  return record.path || record.sequence_path || 'NA';
}

export function Databases({ messages }: { messages: Messages }) {
  const [databases, setDatabases] = useState<DatabaseRecord[]>([]);
  const [selectedName, setSelectedName] = useState('');
  const [registryPath, setRegistryPath] = useState('');
  const [includeHash, setIncludeHash] = useState(false);
  const [checkResult, setCheckResult] = useState<DatabaseRecord | null>(null);
  const [form, setForm] = useState<DatabaseFormState>(defaultForm);
  const [loadingList, setLoadingList] = useState(false);
  const [checking, setChecking] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedDatabase = useMemo(
    () => databases.find((database) => database.name === selectedName) || databases[0] || null,
    [databases, selectedName]
  );

  const availableCount = databases.filter((database) => database.exists).length;
  const missingCount = databases.filter((database) => database.exists === false).length;

  async function loadDatabases(useHash = includeHash) {
    setLoadingList(true);
    setError(null);
    try {
      const loaded = await api.listDatabases(useHash, optionalText(registryPath));
      setDatabases(loaded);
      setSelectedName((current) => {
        if (current && loaded.some((database) => database.name === current)) {
          return current;
        }
        return loaded[0]?.name || '';
      });
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    void loadDatabases(false);
    // Initial load intentionally avoids hashing large FASTA files.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function checkDatabase(name = selectedDatabase?.name || selectedName) {
    const databaseName = name.trim();
    if (!databaseName) {
      return;
    }
    setChecking(true);
    setError(null);
    setNotice(null);
    try {
      const checked = await api.checkDatabase(databaseName, {
        include_hash: includeHash,
        registry_path: optionalText(registryPath)
      });
      setCheckResult(checked);
      setSelectedName(checked.name || databaseName);
      setNotice(checked.message || messages.databases.checkFinished);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setChecking(false);
    }
  }

  async function registerDatabase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRegistering(true);
    setError(null);
    setNotice(null);
    const payload: DatabaseRegistrationPayload = {
      name: form.name.trim(),
      path: form.path.trim(),
      version: optionalText(form.version),
      taxonomy_format: form.taxonomyFormat.trim() || 'sintax',
      database_type: form.databaseType.trim() || 'taxonomy_annotation',
      registry_path: optionalText(registryPath),
      aliases: splitList(form.aliases),
      roles: splitList(form.roles).length ? splitList(form.roles) : ['taxonomy_annotation'],
      sha256: optionalText(form.sha256),
      compute_hash: form.computeHash,
      allow_missing: form.allowMissing,
      overwrite: form.overwrite
    };

    try {
      const registered = await api.registerDatabase(payload);
      setNotice(`${messages.databases.registeredMessage}: ${registered.name}`);
      setCheckResult(registered);
      await loadDatabases(false);
      setSelectedName(registered.name);
      setForm(defaultForm);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setRegistering(false);
    }
  }

  function updateForm<K extends keyof DatabaseFormState>(key: K, value: DatabaseFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function renderTags(values: string[] | undefined, empty = 'NA') {
    if (!values?.length) {
      return <span className="subtle-text">{empty}</span>;
    }
    return (
      <div className="tag-list">
        {values.map((value) => <span className="tag" key={value}>{value}</span>)}
      </div>
    );
  }

  function renderDetails(record: DatabaseRecord | null) {
    if (!record) {
      return (
        <section className="panel">
          <div className="empty-state compact">
            <p>{messages.databases.noSelection}</p>
          </div>
        </section>
      );
    }
    const status = databaseStatus(record, messages);
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.databases.selected}</h2>
          <StatusBadge status={status.status} label={status.label} />
        </div>
        <div className="summary-grid compact-grid">
          <div><span>{messages.databases.name}</span><strong>{record.name}</strong></div>
          <div><span>{messages.databases.version}</span><strong>{record.version || 'NA'}</strong></div>
          <div><span>{messages.databases.source}</span><strong>{record.source || 'NA'}</strong></div>
          <div><span>{messages.databases.taxonomyFormat}</span><strong>{record.taxonomy_format || 'NA'}</strong></div>
          <div><span>{messages.databases.databaseType}</span><strong>{record.type || record.database_type || 'NA'}</strong></div>
          <div><span>{messages.databases.size}</span><strong>{formatBytes(record.size_bytes)}</strong></div>
          <div><span>{messages.databases.modified}</span><strong>{formatDate(record.modified_at)}</strong></div>
          <div><span>{messages.databases.roles}</span>{renderTags(record.roles)}</div>
        </div>
        <div className="database-path-block">
          <span className="muted-label">{messages.databases.path}</span>
          <code>{pathForDisplay(record)}</code>
        </div>
        <div className="database-path-block">
          <span className="muted-label">{messages.databases.aliases}</span>
          {renderTags(record.aliases)}
        </div>
        {record.exists === false ? (
          <div className="warning-block">
            <strong>{messages.databases.missingFile}</strong>
            <p>{messages.databases.missingSuggestion}</p>
          </div>
        ) : null}
      </section>
    );
  }

  function renderCheckResult() {
    if (!checkResult) {
      return null;
    }
    const status = databaseStatus(checkResult, messages);
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.databases.checkResult}</h2>
          <StatusBadge status={status.status} label={status.label} />
        </div>
        <div className="summary-grid compact-grid">
          <div><span>{messages.databases.name}</span><strong>{checkResult.name || checkResult.query || selectedName}</strong></div>
          <div><span>{messages.databases.status}</span><strong>{checkResult.message || status.label}</strong></div>
          <div><span>{messages.databases.size}</span><strong>{formatBytes(checkResult.size_bytes)}</strong></div>
          <div><span>{messages.databases.hashMatch}</span><strong>{checkResult.hash_matches === undefined ? 'NA' : String(checkResult.hash_matches)}</strong></div>
        </div>
        <div className="database-path-block">
          <span className="muted-label">{messages.databases.path}</span>
          <code>{pathForDisplay(checkResult)}</code>
        </div>
        <div className="database-path-block">
          <span className="muted-label">{messages.databases.sha256}</span>
          <code>{checkResult.sha256 || checkResult.sha256_error || messages.databases.noHash}</code>
        </div>
        {checkResult.expected_sha256 ? (
          <div className="database-path-block">
            <span className="muted-label">{messages.databases.expectedSha256}</span>
            <code>{checkResult.expected_sha256}</code>
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>{messages.databases.title}</h1>
          <p>{messages.databases.subtitle}</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={() => loadDatabases()} disabled={loadingList}>
            {loadingList ? messages.loading : messages.refresh}
          </button>
          <button type="button" onClick={() => checkDatabase()} disabled={!selectedDatabase || checking}>
            {checking ? messages.databases.checking : messages.databases.check}
          </button>
        </div>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <section className="panel">
        <div className="form-grid two-columns">
          <label className="field">
            <span>{messages.databases.registryPath}</span>
            <input value={registryPath} onChange={(event) => setRegistryPath(event.target.value)} placeholder="databases.yaml" />
            <small>{messages.databases.registryPathHelp}</small>
          </label>
          <label className="field checkbox-field">
            <input type="checkbox" checked={includeHash} onChange={(event) => setIncludeHash(event.target.checked)} />
            <span>{messages.databases.includeHash}</span>
            <small>{messages.databases.includeHashHelp}</small>
          </label>
        </div>
        <div className="summary-grid compact-grid">
          <div><span>{messages.databases.total}</span><strong>{databases.length}</strong></div>
          <div><span>{messages.databases.available}</span><strong>{availableCount}</strong></div>
          <div><span>{messages.databases.missing}</span><strong>{missingCount}</strong></div>
          <div><span>{messages.databases.registryFile}</span><code>{registryPath.trim() || 'databases.yaml'}</code></div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>{messages.databases.registered}</h2>
          <span className="subtle-text">{databases.length}</span>
        </div>
        {databases.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{messages.databases.name}</th>
                  <th>{messages.databases.version}</th>
                  <th>{messages.databases.source}</th>
                  <th>{messages.databases.taxonomyFormat}</th>
                  <th>{messages.databases.path}</th>
                  <th>{messages.databases.status}</th>
                  <th>{messages.databases.size}</th>
                  <th>{messages.databases.actions}</th>
                </tr>
              </thead>
              <tbody>
                {databases.map((database) => {
                  const status = databaseStatus(database, messages);
                  return (
                    <tr key={`${database.source || 'database'}-${database.name}`}>
                      <td>
                        <button className="link-button" type="button" onClick={() => setSelectedName(database.name)}>
                          <strong>{database.name}</strong>
                        </button>
                        <div className="table-subtext">{database.type || database.database_type || 'NA'}</div>
                      </td>
                      <td>{database.version || 'NA'}</td>
                      <td>{database.source || 'NA'}</td>
                      <td>{database.taxonomy_format || 'NA'}</td>
                      <td><code>{pathForDisplay(database)}</code></td>
                      <td><StatusBadge status={status.status} label={status.label} /></td>
                      <td>{formatBytes(database.size_bytes)}</td>
                      <td>
                        <button type="button" onClick={() => checkDatabase(database.name)} disabled={checking}>
                          {messages.databases.check}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state compact">
            <p>{messages.databases.noDatabases}</p>
            <button type="button" onClick={() => loadDatabases()}>{messages.refresh}</button>
          </div>
        )}
      </section>

      <div className="section-grid two-columns">
        {renderDetails(selectedDatabase)}
        {renderCheckResult()}
      </div>

      <section className="panel">
        <div className="panel-header">
          <h2>{messages.databases.registerLocal}</h2>
          <span className="subtle-text">{messages.databases.noCopyNote}</span>
        </div>
        <form onSubmit={registerDatabase}>
          <div className="form-grid three-columns">
            <label className="field">
              <span>{messages.databases.name}</span>
              <input value={form.name} onChange={(event) => updateForm('name', event.target.value)} required placeholder="custom_16s_db" />
            </label>
            <label className="field">
              <span>{messages.databases.version}</span>
              <input value={form.version} onChange={(event) => updateForm('version', event.target.value)} placeholder="v1" />
            </label>
            <label className="field">
              <span>{messages.databases.taxonomyFormat}</span>
              <select value={form.taxonomyFormat} onChange={(event) => updateForm('taxonomyFormat', event.target.value)}>
                <option value="sintax">sintax</option>
                <option value="qiime2">qiime2</option>
                <option value="rdp">rdp</option>
                <option value="plain">plain</option>
              </select>
            </label>
            <label className="field wide-field">
              <span>{messages.databases.path}</span>
              <input value={form.path} onChange={(event) => updateForm('path', event.target.value)} required placeholder="D:\\reference\\custom.fa" />
              <small>{messages.databases.pathHelp}</small>
            </label>
            <label className="field">
              <span>{messages.databases.databaseType}</span>
              <input value={form.databaseType} onChange={(event) => updateForm('databaseType', event.target.value)} />
            </label>
            <label className="field">
              <span>{messages.databases.aliases}</span>
              <textarea value={form.aliases} onChange={(event) => updateForm('aliases', event.target.value)} placeholder="custom&#10;custom.fa" />
              <small>{messages.databases.aliasesHelp}</small>
            </label>
            <label className="field">
              <span>{messages.databases.roles}</span>
              <textarea value={form.roles} onChange={(event) => updateForm('roles', event.target.value)} />
              <small>{messages.databases.rolesHelp}</small>
            </label>
            <label className="field">
              <span>{messages.databases.sha256}</span>
              <textarea value={form.sha256} onChange={(event) => updateForm('sha256', event.target.value)} />
              <small>{messages.databases.sha256Help}</small>
            </label>
          </div>
          <div className="inline-actions database-options">
            <label className="checkbox-field inline-checkbox">
              <input type="checkbox" checked={form.computeHash} onChange={(event) => updateForm('computeHash', event.target.checked)} />
              <span>{messages.databases.computeHash}</span>
            </label>
            <label className="checkbox-field inline-checkbox">
              <input type="checkbox" checked={form.allowMissing} onChange={(event) => updateForm('allowMissing', event.target.checked)} />
              <span>{messages.databases.allowMissing}</span>
            </label>
            <label className="checkbox-field inline-checkbox">
              <input type="checkbox" checked={form.overwrite} onChange={(event) => updateForm('overwrite', event.target.checked)} />
              <span>{messages.databases.overwrite}</span>
            </label>
            <button className="primary-button" type="submit" disabled={registering || !form.name.trim() || !form.path.trim()}>
              {registering ? messages.databases.registering : messages.databases.register}
            </button>
          </div>
        </form>
      </section>
    </section>
  );
}
