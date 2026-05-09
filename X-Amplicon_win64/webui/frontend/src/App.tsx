import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from './api/client';
import type { DashboardData, Locale, WebUISettings } from './api/types';
import { AppLayout } from './components/AppLayout';
import { getMessages } from './i18n';
import { Agent } from './pages/Agent';
import { Dashboard } from './pages/Dashboard';
import { Databases } from './pages/Databases';
import { NewAnalysis } from './pages/NewAnalysis';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { Results } from './pages/Results';
import { RunMonitor } from './pages/RunMonitor';
import type { PageId } from './pages/pageTypes';
import { Settings } from './pages/Settings';

const emptyDashboardData: DashboardData = {
  health: null,
  settings: null,
  projects: []
};

function pageTitle(page: PageId, messages: ReturnType<typeof getMessages>): string {
  const labels: Record<PageId, string> = {
    dashboard: messages.nav.dashboard,
    newAnalysis: messages.nav.newAnalysis,
    projects: messages.nav.projects,
    runMonitor: messages.nav.runMonitor,
    results: messages.nav.results,
    databases: messages.nav.databases,
    reports: messages.nav.reports,
    agent: messages.nav.agent,
    settings: messages.nav.settings
  };
  return labels[page];
}

export default function App() {
  const [page, setPage] = useState<PageId>('agent');
  const [locale, setLocale] = useState<Locale>('Chinese');
  const [settings, setSettings] = useState<WebUISettings | null>(null);
  const [dashboardData, setDashboardData] = useState<DashboardData>(emptyDashboardData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messages = useMemo(() => getMessages(locale), [locale]);

  const refreshDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [health, loadedSettings, projects] = await Promise.all([
        api.getHealth(),
        api.getSettings(),
        api.listProjects()
      ]);
      setSettings(loadedSettings);
      setLocale(loadedSettings.language);
      setDashboardData({ health, settings: loadedSettings, projects });
    } catch (err) {
      setDashboardData(emptyDashboardData);
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshDashboard();
  }, [refreshDashboard]);

  useEffect(() => {
    document.documentElement.lang = locale === 'Chinese' ? 'zh-CN' : 'en';
    document.body.dataset.locale = locale;
  }, [locale]);

  async function handleLocaleChange(nextLocale: Locale) {
    setLocale(nextLocale);
    if (!settings) {
      return;
    }
    const nextSettings = { ...settings, language: nextLocale };
    setSettings(nextSettings);
    setDashboardData((current) => ({ ...current, settings: nextSettings }));
    try {
      const saved = await api.saveSettings(nextSettings);
      setSettings(saved);
      setDashboardData((current) => ({ ...current, settings: saved }));
    } catch {
      // The language switch should remain usable even when the backend is offline.
    }
  }

  function handleSettingsSaved(saved: WebUISettings) {
    setSettings(saved);
    setLocale(saved.language);
    setDashboardData((current) => ({ ...current, settings: saved }));
  }

  const backendConnected = Boolean(dashboardData.health);

  let content;
  if (page === 'dashboard') {
    content = (
      <Dashboard
        data={dashboardData}
        loading={loading}
        error={error}
        messages={messages}
        onNavigate={setPage}
        onRefresh={refreshDashboard}
      />
    );
  } else if (page === 'newAnalysis') {
    content = (
      <NewAnalysis
        settings={settings}
        projectRoot={dashboardData.health?.cwd || null}
        messages={messages}
        onNavigate={setPage}
        onProjectSaved={refreshDashboard}
      />
    );
  } else if (page === 'settings') {
    content = <Settings settings={settings} messages={messages} onSettingsSaved={handleSettingsSaved} />;
  } else if (page === 'runMonitor') {
    content = <RunMonitor projects={dashboardData.projects} messages={messages} onNavigate={setPage} />;
  } else if (page === 'results') {
    content = <Results projects={dashboardData.projects} messages={messages} onNavigate={setPage} />;
  } else if (page === 'databases') {
    content = <Databases messages={messages} />;
  } else if (page === 'agent') {
    content = <Agent projects={dashboardData.projects} locale={locale} messages={messages} onNavigate={setPage} />;
  } else {
    content = <PlaceholderPage title={pageTitle(page, messages)} messages={messages} />;
  }

  return (
    <AppLayout
      currentPage={page}
      locale={locale}
      messages={messages}
      backendConnected={backendConnected}
      onNavigate={setPage}
      onLocaleChange={handleLocaleChange}
    >
      {content}
    </AppLayout>
  );
}
