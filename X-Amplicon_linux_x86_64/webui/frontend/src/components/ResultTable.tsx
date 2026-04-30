import { useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type { Messages } from '../i18n';

interface ResultTableProps {
  path: string | null | undefined;
  projectId?: string | null;
  messages: Messages;
  maxRows?: number;
}

function parseDelimited(text: string, maxRows: number): { columns: string[]; rows: string[][] } {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (!lines.length) {
    return { columns: [], rows: [] };
  }
  const delimiter = lines[0].includes('\t') ? '\t' : ',';
  const columns = lines[0].split(delimiter);
  const rows = lines.slice(1, maxRows + 1).map((line) => line.split(delimiter));
  return { columns, rows };
}

export function ResultTable({ path, projectId, messages, maxRows = 20 }: ResultTableProps) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!path) {
        setText('');
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const response = await api.readFile(path, projectId);
        if (!cancelled) {
          setText(response.text);
        }
      } catch (err) {
        if (!cancelled) {
          setError(formatApiError(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [path, projectId]);

  const table = useMemo(() => parseDelimited(text, maxRows), [maxRows, text]);

  if (!path) {
    return <div className="empty-state compact"><p>{messages.results.tableMissing}</p></div>;
  }
  if (loading) {
    return <div className="empty-state compact"><p>{messages.loading}</p></div>;
  }
  if (error) {
    return <div className="alert alert-error">{error}</div>;
  }
  if (!table.columns.length) {
    return <div className="empty-state compact"><p>{messages.results.emptyTable}</p></div>;
  }

  return (
    <div className="table-preview">
      <div className="table-preview-header">
        <span>{messages.results.previewRows.replace('{count}', String(table.rows.length))}</span>
        <a className="button-link" href={api.fileDownloadUrl(path, projectId)}>
          {messages.results.download}
        </a>
      </div>
      <div className="table-wrap">
        <table className="data-table compact-table">
          <thead>
            <tr>
              {table.columns.map((column, index) => (
                <th key={`${column}-${index}`}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {table.columns.map((_, columnIndex) => (
                  <td key={columnIndex}>{row[columnIndex] || ''}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
