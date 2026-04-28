import { api } from '../api/client';
import type { Messages } from '../i18n';

interface PlotFrameProps {
  title: string;
  path: string | null | undefined;
  projectId?: string | null;
  messages: Messages;
}

export function PlotFrame({ title, path, projectId, messages }: PlotFrameProps) {
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
        </div>
      </div>
      <iframe className="plot-frame" title={title} src={viewUrl} />
    </section>
  );
}
