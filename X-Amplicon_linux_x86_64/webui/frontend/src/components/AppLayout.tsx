import type { ReactNode } from 'react';

import type { Locale } from '../api/types';
import type { Messages } from '../i18n';
import type { PageId } from '../pages/pageTypes';
import { StatusBadge } from './StatusBadge';

interface NavItem {
  id: PageId;
  label: string;
}

interface AppLayoutProps {
  currentPage: PageId;
  locale: Locale;
  messages: Messages;
  backendConnected: boolean;
  onNavigate: (page: PageId) => void;
  onLocaleChange: (locale: Locale) => void;
  children: ReactNode;
}

export function AppLayout({
  currentPage,
  locale,
  messages,
  backendConnected,
  onNavigate,
  onLocaleChange,
  children
}: AppLayoutProps) {
  const navItems: NavItem[] = [
    { id: 'agent', label: messages.nav.agent },
    { id: 'newAnalysis', label: messages.nav.newAnalysis },
    { id: 'runMonitor', label: messages.nav.runMonitor },
    { id: 'results', label: messages.nav.results },
    { id: 'databases', label: messages.nav.databases },
    { id: 'dashboard', label: messages.nav.dashboard },
    { id: 'settings', label: messages.nav.settings }
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">XA</div>
          <div>
            <div className="brand-name">{messages.appName}</div>
            <div className="brand-subtitle">{messages.appSubtitle}</div>
          </div>
        </div>

        <nav className="nav-list" aria-label="Primary">
          {navItems.map((item) => (
            <button
              className={`nav-item${currentPage === item.id ? ' active' : ''}`}
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
            >
              <span className="nav-dot" aria-hidden="true" />
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="topbar-status">
            <span className="muted-label">{messages.backend}</span>
            <StatusBadge
              status={backendConnected ? 'ok' : 'failed'}
              label={backendConnected ? messages.connected : messages.disconnected}
            />
          </div>
          <label className="language-control">
            <span>{messages.language}</span>
            <select value={locale} onChange={(event) => onLocaleChange(event.target.value as Locale)}>
              <option value="Chinese">{messages.chinese}</option>
              <option value="English">{messages.english}</option>
            </select>
          </label>
        </header>

        <main className="content-area">{children}</main>
      </div>
    </div>
  );
}
