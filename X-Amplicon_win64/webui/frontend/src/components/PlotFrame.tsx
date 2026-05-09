import { api } from '../api/client';
import type { Messages } from '../i18n';

interface PlotFrameProps {
  title: string;
  path: string | null | undefined;
  projectId?: string | null;
  messages: Messages;
  formats?: Partial<Record<string, string>> | null;
}

function suffixOf(path: string): string {
  const name = path.replace(/\\/g, '/').split('/').pop() || path;
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index + 1).toLowerCase() : '';
}

function formatLabel(format: string): string {
  return format.toUpperCase();
}

export function PlotFrame({ title, path, projectId, messages, formats }: PlotFrameProps) {
  if (!path) {
    return (
      <section className="plot-panel">
        <div className="empty-state compact">
          <p>{messages.results.plotMissing}</p>
        </div>
      </section>
    );
  }

  const viewUrl = api.fileViewUrl(path, projectId);
  const downloadUrl = api.fileDownloadUrl(path, projectId);
  const suffix = suffixOf(path);
  const formatEntries = Object.entries(formats || {}).filter((entry): entry is [string, string] => Boolean(entry[1]));

  return (
    <section className="plot-panel">
      <div className="plot-header">
        <div>
          <h3>{title}</h3>
          <code>{path}</code>
        </div>
        <div className="inline-actions">
          <a className="button-link" href={viewUrl} target="_blank" rel="noreferrer">
            {messages.results.openNewWindow}
          </a>
          <a className="button-link" href={downloadUrl}>
            {messages.results.download}
          </a>
          {formatEntries.map(([format, formatPath]) => (
            <a className="button-link" href={api.fileDownloadUrl(formatPath, projectId)} key={`${format}-${formatPath}`}>
              {formatLabel(format)}
            </a>
          ))}
        </div>
      </div>
      {suffix === 'html' || suffix === 'htm' ? <iframe className="plot-frame" title={title} src={viewUrl} /> : null}
      {suffix === 'png' || suffix === 'svg' ? <img className="plot-frame plot-image" src={viewUrl} alt={title} /> : null}
      {suffix !== 'html' && suffix !== 'htm' && suffix !== 'png' && suffix !== 'svg' ? (
        <div className="empty-state compact">
          <p>{messages.results.staticPlotDownload}</p>
        </div>
      ) : null}
    </section>
  );
}
