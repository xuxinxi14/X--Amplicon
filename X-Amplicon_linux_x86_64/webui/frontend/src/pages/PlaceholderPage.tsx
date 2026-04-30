import type { Messages } from '../i18n';

interface PlaceholderPageProps {
  title: string;
  messages: Messages;
}

export function PlaceholderPage({ title, messages }: PlaceholderPageProps) {
  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>{title}</h1>
          <p>{messages.placeholder.body}</p>
        </div>
      </div>
      <div className="empty-state">
        <h2>{messages.placeholder.title}</h2>
        <p>{messages.placeholder.body}</p>
      </div>
    </section>
  );
}
