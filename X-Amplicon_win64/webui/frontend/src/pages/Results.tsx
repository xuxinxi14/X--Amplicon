import { useCallback, useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type {
  DifferentialComparisonResult,
  FileEntry,
  JobRecord,
  ProjectRecord,
  ResultFigure,
  ResultIndex
} from '../api/types';
import { PlotFrame } from '../components/PlotFrame';
import { ResultTable } from '../components/ResultTable';
import { StatusBadge } from '../components/StatusBadge';
import type { Messages } from '../i18n';
import type { PageId } from './pageTypes';

type ResultTab = 'summary' | 'qc' | 'alpha' | 'beta' | 'taxonomy' | 'differential' | 'report' | 'provenance' | 'files';

interface ResultsProps {
  projects: ProjectRecord[];
  messages: Messages;
  onNavigate: (page: PageId) => void;
}

interface ProjectOption {
  id: string;
  label: string;
  projectIdForFiles: string | null;
  realProject: ProjectRecord | null;
}

const tabs: ResultTab[] = ['summary', 'qc', 'alpha', 'beta', 'taxonomy', 'differential', 'report', 'provenance', 'files'];
const taxonomyLevels = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species'];
const betaMetrics = ['braycurtis', 'euclidean', 'jaccard', 'manhattan', 'unweighted_unifrac', 'weighted_unifrac'];
const alphaMetrics = ['richness', 'chao1', 'ace', 'shannon', 'simpson', 'invsimpson'];

function safeJson(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function normalizePath(path: string): string {
  return path.replace(/\\/g, '/').toLowerCase();
}

function fileName(path: string | null | undefined): string {
  if (!path) {
    return 'NA';
  }
  return path.replace(/\\/g, '/').split('/').pop() || path;
}

function findFigure(figures: ResultFigure[], keywords: string[]): ResultFigure | null {
  const lowered = keywords.map((item) => item.toLowerCase());
  return figures.find((figure) => {
    const haystack = `${figure.label} ${normalizePath(figure.path)}`;
    return lowered.every((keyword) => haystack.includes(keyword));
  }) || null;
}

function findFigurePath(figures: ResultFigure[], fragment: string): ResultFigure | null {
  const lowered = fragment.toLowerCase().replace(/\.(html?|png|svg|pdf)$/, '');
  return figures.find((figure) => normalizePath(figure.path).includes(lowered)) || null;
}

function pathJoin(root: string, ...parts: string[]): string {
  const sep = root.includes('\\') ? '\\' : '/';
  return [root.replace(/[\\/]+$/, ''), ...parts].join(sep);
}

function directionText(comparison: string, messages: Messages): string {
  const normalized = comparison.replace('_vs_', ':').replace('_VS_', ':');
  const [caseGroup, controlGroup] = normalized.split(':');
  if (!caseGroup || !controlGroup) {
    return comparison;
  }
  return `${caseGroup} ${messages.results.relativeTo} ${controlGroup}`;
}

function formatBytes(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function isPreviewable(entry: FileEntry): boolean {
  return /\.(txt|tsv|csv|json|jsonl|yaml|yml|md|html|htm|log)$/i.test(entry.name);
}

function statusText(status: string, messages: Messages): string {
  const labels = messages.runMonitor.statusLabels as Record<string, string>;
  return labels[status] || status;
}

export function Results({ projects, messages, onNavigate }: ResultsProps) {
  const projectOptions = useMemo<ProjectOption[]>(
    () => [
      {
        id: 'current',
        label: messages.results.currentWorkspace,
        projectIdForFiles: null,
        realProject: null
      },
      ...projects.map((project) => ({
        id: project.id,
        label: project.name,
        projectIdForFiles: project.id,
        realProject: project
      }))
    ],
    [messages.results.currentWorkspace, projects]
  );

  const defaultProjectId = projectOptions.find((option) => option.realProject)?.id || 'current';
  const [selectedProjectId, setSelectedProjectId] = useState(defaultProjectId);
  const [projectSelectionTouched, setProjectSelectionTouched] = useState(false);
  const [activeTab, setActiveTab] = useState<ResultTab>('summary');
  const [resultIndex, setResultIndex] = useState<ResultIndex | null>(null);
  const [summaryText, setSummaryText] = useState('');
  const [provenanceText, setProvenanceText] = useState('');
  const [alphaMetric, setAlphaMetric] = useState('shannon');
  const [betaMetric, setBetaMetric] = useState('braycurtis');
  const [taxonomyLevel, setTaxonomyLevel] = useState('phylum');
  const [comparison, setComparison] = useState('');
  const [filesPath, setFilesPath] = useState('');
  const [fileEntries, setFileEntries] = useState<FileEntry[]>([]);
  const [fileSearch, setFileSearch] = useState('');
  const [previewText, setPreviewText] = useState('');
  const [loading, setLoading] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resultWarnings, setResultWarnings] = useState<string[]>([]);
  const [reportJob, setReportJob] = useState<JobRecord | null>(null);

  const selectedOption = projectOptions.find((item) => item.id === selectedProjectId) || projectOptions[0];
  const projectIdForFiles = selectedOption?.projectIdForFiles || null;

  const loadResults = useCallback(async () => {
    if (!selectedOption) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    setResultWarnings([]);
    setSummaryText('');
    setProvenanceText('');
    setPreviewText('');
    try {
      const index = await api.getResults(selectedOption.id);
      setResultIndex(index);
      setFilesPath(index.final_dir);
      setComparison(index.differential[0]?.comparison || '');
      if (index.summary_path) {
        try {
          const summary = await api.readFile(index.summary_path, projectIdForFiles);
          setSummaryText(summary.text);
        } catch (err) {
          setSummaryText('');
          setResultWarnings((current) => [...current, `${messages.results.summaryReadFailed}: ${formatApiError(err)}`]);
        }
      }
      if (index.provenance_markdown) {
        try {
          const provenance = await api.readFile(index.provenance_markdown, projectIdForFiles);
          setProvenanceText(provenance.text);
        } catch (err) {
          setProvenanceText('');
          setResultWarnings((current) => [...current, `${messages.results.provenanceReadFailed}: ${formatApiError(err)}`]);
        }
      }
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }, [messages.results.provenanceReadFailed, messages.results.summaryReadFailed, projectIdForFiles, selectedOption]);

  const loadFiles = useCallback(
    async (path = filesPath) => {
      if (!path) {
        setFileEntries([]);
        return;
      }
      setFileLoading(true);
      setError(null);
      try {
        const listed = await api.listFiles(path, projectIdForFiles);
        setFilesPath(listed.path);
        setFileEntries(listed.entries);
      } catch (err) {
        setError(formatApiError(err));
      } finally {
        setFileLoading(false);
      }
    },
    [filesPath, projectIdForFiles]
  );

  useEffect(() => {
    if (!projectOptions.find((item) => item.id === selectedProjectId)) {
      setSelectedProjectId(defaultProjectId);
      return;
    }
    if (!projectSelectionTouched && selectedProjectId === 'current' && defaultProjectId !== 'current') {
      setSelectedProjectId(defaultProjectId);
    }
  }, [defaultProjectId, projectOptions, projectSelectionTouched, selectedProjectId]);

  useEffect(() => {
    void loadResults();
  }, [loadResults]);

  useEffect(() => {
    if (activeTab === 'files' && resultIndex?.available) {
      void loadFiles(resultIndex.final_dir);
    }
  }, [activeTab, resultIndex, loadFiles]);

  const summaryJson = useMemo(() => safeJson(summaryText), [summaryText]);
  const effectiveParams = asRecord(summaryJson?.effective_params);
  const steps = Array.isArray(summaryJson?.steps) ? summaryJson.steps as Record<string, unknown>[] : [];
  const sampleCount = steps
    .map((step) => asRecord(step.details).sample_count)
    .find((value) => typeof value === 'number') || asRecord(safeJson(provenanceText)?.workflow).sample_count;
  const alphaFigures = resultIndex?.figures.alpha || [];
  const betaFigures = resultIndex?.figures.beta || [];
  const taxonomyFigures = resultIndex?.figures.taxonomy || [];
  const selectedComparison = resultIndex?.differential.find((item) => item.comparison === comparison) || null;

  function setSelectedProject(nextProjectId: string) {
    setProjectSelectionTouched(true);
    setSelectedProjectId(nextProjectId);
    setResultIndex(null);
    setSummaryText('');
    setProvenanceText('');
    setFileEntries([]);
    setPreviewText('');
    setResultWarnings([]);
  }

  async function startReport() {
    if (!selectedOption?.realProject) {
      setError(messages.results.reportNeedsProject);
      return;
    }
    setError(null);
    setNotice(null);
    try {
      const job = await api.startReport(selectedOption.realProject.id);
      setReportJob(job);
      setNotice(messages.results.reportStarted);
    } catch (err) {
      setError(formatApiError(err));
    }
  }

  async function previewFile(entry: FileEntry) {
    setPreviewText('');
    if (entry.is_dir) {
      await loadFiles(entry.path);
      return;
    }
    if (!isPreviewable(entry) || entry.size > 1_500_000) {
      setNotice(messages.results.fileTooLarge);
      return;
    }
    try {
      const response = await api.readFile(entry.path, projectIdForFiles);
      setPreviewText(response.text.slice(0, 80_000));
    } catch (err) {
      setError(formatApiError(err));
    }
  }

  async function copyCommand() {
    const paramsSource = effectiveParams.params_source;
    if (typeof paramsSource !== 'string' || !paramsSource) {
      return;
    }
    const command = `python process.py run-pipeline-config --params "${paramsSource}"`;
    await navigator.clipboard.writeText(command);
    setNotice(messages.results.commandCopied);
  }

  function renderUnavailable() {
    return (
      <section className="panel">
        <div className="empty-state compact">
          <p>{resultIndex?.messages[0] || messages.results.noResults}</p>
          <button className="primary-button" type="button" onClick={() => onNavigate('newAnalysis')}>
            {messages.nav.newAnalysis}
          </button>
        </div>
      </section>
    );
  }

  function renderSummary() {
    if (!resultIndex?.available) {
      return renderUnavailable();
    }
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.summary}</h2>
          <StatusBadge status={String(summaryJson?.status || 'ok')} label={statusText(String(summaryJson?.status || 'ok'), messages)} />
        </div>
        <div className="summary-grid">
          <div><span>{messages.results.samples}</span><strong>{String(sampleCount || 'NA')}</strong></div>
          <div><span>{messages.results.database}</span><strong>{String(effectiveParams.annotation_database || 'NA')}</strong></div>
          <div><span>{messages.results.featureMethod}</span><strong>{String(effectiveParams.feature_method || 'NA')}</strong></div>
          <div><span>{messages.results.outputDir}</span><code>{resultIndex.final_dir}</code></div>
          <div><span>{messages.results.startedAt}</span><strong>{String(summaryJson?.started_at || 'NA')}</strong></div>
          <div><span>{messages.results.figures}</span><strong>{String(Object.values(resultIndex.figures).flat().length)}</strong></div>
        </div>
        <div className="result-shortcuts">
          {resultIndex.plots_index ? <button type="button" onClick={() => setActiveTab('alpha')}>{messages.results.tabs.alpha}</button> : null}
          {resultIndex.report_html ? <button type="button" onClick={() => setActiveTab('report')}>{messages.results.report}</button> : null}
          {resultIndex.provenance_json ? <button type="button" onClick={() => setActiveTab('provenance')}>{messages.results.tabs.provenance}</button> : null}
        </div>
        <PlotFrame title={messages.results.plotIndex} path={resultIndex.plots_index} projectId={projectIdForFiles} messages={messages} />
      </section>
    );
  }

  function renderQc() {
    if (!resultIndex?.available) {
      return renderUnavailable();
    }
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.qc}</h2>
          <span className="subtle-text">{steps.length} {messages.results.steps}</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{messages.results.step}</th>
                <th>{messages.results.status}</th>
                <th>{messages.results.duration}</th>
                <th>{messages.results.details}</th>
              </tr>
            </thead>
            <tbody>
              {steps.map((step, index) => (
                <tr key={`${String(step.name)}-${index}`}>
                  <td><strong>{String(step.name || 'NA')}</strong></td>
                  <td><StatusBadge status={String(step.status || 'unknown')} label={statusText(String(step.status || 'unknown'), messages)} /></td>
                  <td>{String(step.duration_seconds ?? 'NA')}</td>
                  <td><code>{JSON.stringify(step.details || {})}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <section className="soft-panel">
          <h3>{messages.results.keyFiles}</h3>
          <div className="result-file-grid">
            {Object.entries(resultIndex.files).map(([key, path]) => (
              <a className="button-link" href={path ? api.fileDownloadUrl(path, projectIdForFiles) : undefined} key={key}>
                {key}: {path ? fileName(path) : messages.results.missing}
              </a>
            ))}
          </div>
        </section>
      </section>
    );
  }

  function renderAlpha() {
    const boxplot = findFigurePath(alphaFigures, `alpha_boxplot_${alphaMetric}.html`);
    const barplot = findFigurePath(alphaFigures, `alpha_barplot_${alphaMetric}.html`);
    const rare = findFigurePath(alphaFigures, 'alpha_rarefaction_curve.html') || findFigure(alphaFigures, ['rarefaction']);
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.tabs.alpha}</h2>
          <label className="compact-select">
            <span>{messages.results.metric}</span>
            <select value={alphaMetric} onChange={(event) => setAlphaMetric(event.target.value)}>
              {alphaMetrics.map((metric) => <option key={metric} value={metric}>{metric}</option>)}
            </select>
          </label>
        </div>
        <PlotFrame title={`${messages.results.boxplot} - ${alphaMetric}`} path={boxplot?.path} projectId={projectIdForFiles} messages={messages} formats={boxplot?.formats} />
        <PlotFrame title={`${messages.results.barplot} - ${alphaMetric}`} path={barplot?.path} projectId={projectIdForFiles} messages={messages} formats={barplot?.formats} />
        <PlotFrame title={messages.results.rarefaction} path={rare?.path} projectId={projectIdForFiles} messages={messages} formats={rare?.formats} />
        <ResultTable path={resultIndex?.files.alpha_diversity} projectId={projectIdForFiles} messages={messages} />
      </section>
    );
  }

  function renderBeta() {
    const pcoa = findFigurePath(betaFigures, `beta_pcoa_${betaMetric}.html`);
    const cpcoa = findFigurePath(betaFigures, `beta_cpcoa_${betaMetric}.html`);
    const heatmap = findFigurePath(betaFigures, `beta_heatmap_${betaMetric}.html`);
    const betaMatrix = resultIndex ? pathJoin(resultIndex.final_dir, 'beta', `${betaMetric}.tsv`) : null;
    const stats = resultIndex ? pathJoin(resultIndex.final_dir, 'plots', 'beta_heatmap_chart', 'beta_stat_results.tsv') : null;
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.tabs.beta}</h2>
          <label className="compact-select">
            <span>{messages.results.metric}</span>
            <select value={betaMetric} onChange={(event) => setBetaMetric(event.target.value)}>
              {betaMetrics.map((metric) => <option key={metric} value={metric}>{metric}</option>)}
            </select>
          </label>
        </div>
        <PlotFrame title={`PCoA - ${betaMetric}`} path={pcoa?.path} projectId={projectIdForFiles} messages={messages} formats={pcoa?.formats} />
        <PlotFrame title={`CPCoA - ${betaMetric}`} path={cpcoa?.path} projectId={projectIdForFiles} messages={messages} formats={cpcoa?.formats} />
        <PlotFrame title={`${messages.results.heatmap} - ${betaMetric}`} path={heatmap?.path} projectId={projectIdForFiles} messages={messages} formats={heatmap?.formats} />
        <section className="soft-panel">
          <h3>{messages.results.groupTest}</h3>
          <ResultTable path={stats} projectId={projectIdForFiles} messages={messages} />
          {betaMatrix ? <a className="button-link" href={api.fileDownloadUrl(betaMatrix, projectIdForFiles)}>{messages.results.downloadDistanceMatrix}</a> : null}
        </section>
      </section>
    );
  }

  function renderTaxonomy() {
    const stacked =
      findFigurePath(taxonomyFigures, `taxonomy_stacked_bar_${taxonomyLevel}.html`)
      || findFigure(taxonomyFigures, ['stacked', taxonomyLevel]);
    const heatmap = findFigurePath(taxonomyFigures, `taxonomy_heatmap_${taxonomyLevel}.html`);
    const summary = resultIndex ? pathJoin(resultIndex.final_dir, 'taxonomy_summary', `${taxonomyLevel}.tsv`) : null;
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.tabs.taxonomy}</h2>
          <label className="compact-select">
            <span>{messages.results.level}</span>
            <select value={taxonomyLevel} onChange={(event) => setTaxonomyLevel(event.target.value)}>
              {taxonomyLevels.map((level) => <option key={level} value={level}>{level}</option>)}
            </select>
          </label>
        </div>
        <PlotFrame title={`${messages.results.stackedBar} - ${taxonomyLevel}`} path={stacked?.path} projectId={projectIdForFiles} messages={messages} formats={stacked?.formats} />
        <PlotFrame title={`${messages.results.heatmap} - ${taxonomyLevel}`} path={heatmap?.path} projectId={projectIdForFiles} messages={messages} formats={heatmap?.formats} />
        <ResultTable path={summary} projectId={projectIdForFiles} messages={messages} />
      </section>
    );
  }

  function renderDifferential() {
    const item: DifferentialComparisonResult | null = selectedComparison;
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.tabs.differential}</h2>
          <label className="compact-select">
            <span>{messages.results.comparison}</span>
            <select value={comparison} onChange={(event) => setComparison(event.target.value)}>
              {(resultIndex?.differential || []).map((diff) => <option key={diff.comparison} value={diff.comparison}>{diff.comparison}</option>)}
            </select>
          </label>
        </div>
        {!item ? <div className="empty-state compact"><p>{messages.results.noDifferential}</p></div> : (
          <>
            <div className="summary-grid">
              <div><span>{messages.results.direction}</span><strong>{directionText(item.comparison, messages)}</strong></div>
              <div><span>{messages.results.testedFeatures}</span><strong>{String(item.tested_features ?? 'NA')}</strong></div>
              <div><span>{messages.results.significantFeatures}</span><strong>{String(item.significant_features ?? 0)}</strong></div>
            </div>
            {item.significant_features === 0 ? <div className="alert alert-success">{messages.results.noSignificant}</div> : null}
            <PlotFrame title={`${messages.results.volcano} - ${item.comparison}`} path={item.volcano} projectId={projectIdForFiles} messages={messages} formats={item.volcano_formats} />
            <PlotFrame title={`${messages.results.heatmap} - ${item.comparison}`} path={item.heatmap} projectId={projectIdForFiles} messages={messages} formats={item.heatmap_formats} />
            <section className="soft-panel">
              <h3>{messages.results.resultTable}</h3>
              <ResultTable path={item.result_path} projectId={projectIdForFiles} messages={messages} maxRows={15} />
            </section>
            <section className="soft-panel">
              <h3>{messages.results.significantTable}</h3>
              <ResultTable path={item.significant_path} projectId={projectIdForFiles} messages={messages} maxRows={15} />
            </section>
          </>
        )}
      </section>
    );
  }

  function renderReport() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.report}</h2>
          <div className="inline-actions">
            <button type="button" onClick={startReport}>{messages.results.generateReport}</button>
            {reportJob ? <button type="button" onClick={() => onNavigate('runMonitor')}>{messages.nav.runMonitor}</button> : null}
          </div>
        </div>
        {reportJob ? <div className="alert alert-success">{messages.results.reportStarted}: <code>{reportJob.id}</code></div> : null}
        <PlotFrame title={messages.results.reportHtml} path={resultIndex?.report_html} projectId={projectIdForFiles} messages={messages} />
        <div className="result-file-grid">
          {resultIndex?.report_markdown ? <a className="button-link" href={api.fileDownloadUrl(resultIndex.report_markdown, projectIdForFiles)}>analysis_report.md</a> : null}
          {resultIndex?.report_data ? <a className="button-link" href={api.fileDownloadUrl(resultIndex.report_data, projectIdForFiles)}>report_data.json</a> : null}
        </div>
      </section>
    );
  }

  function renderProvenance() {
    const paramsSource = effectiveParams.params_source;
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.tabs.provenance}</h2>
          <div className="inline-actions">
            <button type="button" onClick={copyCommand} disabled={typeof paramsSource !== 'string'}>
              {messages.results.copyReproduceCommand}
            </button>
            {resultIndex?.provenance_json ? <a className="button-link" href={api.fileDownloadUrl(resultIndex.provenance_json, projectIdForFiles)}>provenance.json</a> : null}
            {resultIndex?.summary_path ? <a className="button-link" href={api.fileDownloadUrl(resultIndex.summary_path, projectIdForFiles)}>run_summary.json</a> : null}
          </div>
        </div>
        {provenanceText ? <pre className="markdown-preview">{provenanceText}</pre> : <div className="empty-state compact"><p>{messages.results.provenanceMissing}</p></div>}
      </section>
    );
  }

  function renderFiles() {
    const filtered = fileEntries.filter((entry) => entry.name.toLowerCase().includes(fileSearch.toLowerCase()));
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{messages.results.files}</h2>
          <button type="button" onClick={() => loadFiles()} disabled={fileLoading}>{fileLoading ? messages.loading : messages.refresh}</button>
        </div>
        <div className="form-grid two-columns">
          <label className="field">
            <span>{messages.results.currentFolder}</span>
            <input value={filesPath} onChange={(event) => setFilesPath(event.target.value)} />
          </label>
          <label className="field">
            <span>{messages.results.searchFiles}</span>
            <input value={fileSearch} onChange={(event) => setFileSearch(event.target.value)} />
          </label>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{messages.results.name}</th>
                <th>{messages.results.type}</th>
                <th>{messages.results.size}</th>
                <th>{messages.results.actions}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry) => (
                <tr key={entry.path}>
                  <td><button className="link-button" type="button" onClick={() => previewFile(entry)}>{entry.name}</button></td>
                  <td>{entry.is_dir ? messages.results.folder : messages.results.file}</td>
                  <td>{entry.is_dir ? '' : formatBytes(entry.size)}</td>
                  <td>
                    <div className="inline-actions">
                      {entry.is_dir ? <button type="button" onClick={() => loadFiles(entry.path)}>{messages.open}</button> : null}
                      {!entry.is_dir && /\.html?$/i.test(entry.name) ? <a className="button-link" href={api.fileViewUrl(entry.path, projectIdForFiles)} target="_blank" rel="noreferrer">{messages.results.openHtml}</a> : null}
                      {!entry.is_dir ? <a className="button-link" href={api.fileDownloadUrl(entry.path, projectIdForFiles)}>{messages.results.download}</a> : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {previewText ? (
          <section className="soft-panel">
            <h3>{messages.results.preview}</h3>
            <pre className="markdown-preview">{previewText}</pre>
          </section>
        ) : null}
      </section>
    );
  }

  function renderActiveTab() {
    if (loading) {
      return <section className="panel"><div className="empty-state compact"><p>{messages.loading}</p></div></section>;
    }
    if (!resultIndex?.available && activeTab !== 'summary') {
      return renderUnavailable();
    }
    if (activeTab === 'summary') return renderSummary();
    if (activeTab === 'qc') return renderQc();
    if (activeTab === 'alpha') return renderAlpha();
    if (activeTab === 'beta') return renderBeta();
    if (activeTab === 'taxonomy') return renderTaxonomy();
    if (activeTab === 'differential') return renderDifferential();
    if (activeTab === 'report') return renderReport();
    if (activeTab === 'provenance') return renderProvenance();
    return renderFiles();
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>{messages.results.title}</h1>
          <p>{messages.results.subtitle}</p>
        </div>
        <div className="inline-actions">
          <select value={selectedProjectId} onChange={(event) => setSelectedProject(event.target.value)}>
            {projectOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
          </select>
          <button type="button" onClick={loadResults}>{messages.refresh}</button>
        </div>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}
      {resultWarnings.map((warning) => <div className="alert alert-warning" key={warning}>{warning}</div>)}

      <div className="tabs">
        {tabs.map((tab) => (
          <button className={`tab-button${activeTab === tab ? ' active' : ''}`} type="button" key={tab} onClick={() => setActiveTab(tab)}>
            {messages.results.tabs[tab]}
          </button>
        ))}
      </div>

      {renderActiveTab()}
    </section>
  );
}
