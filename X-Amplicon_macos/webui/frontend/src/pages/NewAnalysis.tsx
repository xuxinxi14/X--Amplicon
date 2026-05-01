import { useEffect, useMemo, useState } from 'react';

import { api, formatApiError } from '../api/client';
import type {
  DatabaseRecord,
  FastqPairingPreview,
  JobRecord,
  MetadataValidationResult,
  ParamsWriteResult,
  PipelineParamsDraft,
  ProjectRecord,
  WebUISettings
} from '../api/types';
import { StatusBadge } from '../components/StatusBadge';
import type { Messages } from '../i18n';
import type { PageId } from './pageTypes';

type WizardStep = 'project' | 'inputs' | 'groups' | 'analysis' | 'run';

interface NewAnalysisProps {
  settings: WebUISettings | null;
  projectRoot: string | null;
  messages: Messages;
  onNavigate: (page: PageId) => void;
  onProjectSaved: (project: ProjectRecord) => void;
}

interface ProjectForm {
  name: string;
  project_dir: string;
  output_root: string;
  analysis_type: string;
}

interface InputForm {
  metadata_path: string;
  seq_dir: string;
  sample_id_col: string;
  group_col: string;
  read1_suffix: string;
  read2_suffix: string;
}

interface AnalysisForm {
  feature_method: NonNullable<PipelineParamsDraft['feature_method']>;
  chimera_mode: NonNullable<PipelineParamsDraft['chimera_mode']>;
  reference_db: string;
  annotation_database: string;
  otutab_method: NonNullable<PipelineParamsDraft['otutab_method']>;
  filter_route: NonNullable<PipelineParamsDraft['filter_route']>;
  fastq_stripleft: number;
  fastq_stripright: number;
  fastq_maxee_rate: number;
  feature_minsize: number;
  feature_identity: number;
  otutab_identity: number;
  sintax_cutoff: number;
  rarefaction_depth: number;
  rarefaction_seed: number;
  threads: number;
  beta_tree_path: string;
  command_timeout: string;
  color_palette: string;
}

const steps: WizardStep[] = ['project', 'inputs', 'groups', 'analysis', 'run'];

const readSuffixOptions = ['_1.fq.gz', '_R1.fastq.gz', '_R1.fq.gz', '_1.fastq.gz'];
const read2SuffixOptions = ['_2.fq.gz', '_R2.fastq.gz', '_R2.fq.gz', '_2.fastq.gz'];

function projectDefaults(settings: WebUISettings | null, projectRoot: string | null, messages: Messages): ProjectForm {
  return {
    name: `${messages.newAnalysis.title} ${new Date().toISOString().slice(0, 10)}`,
    project_dir: projectRoot || '',
    output_root: settings?.default_output_root || 'work',
    analysis_type: '16S rRNA'
  };
}

function inputDefaults(settings: WebUISettings | null): InputForm {
  return {
    metadata_path: settings?.default_metadata_path || 'metadata.txt',
    seq_dir: settings?.default_seq_dir || 'seq',
    sample_id_col: settings?.default_sample_id_col || 'SampleID',
    group_col: settings?.default_group_col || 'Group',
    read1_suffix: '_1.fq.gz',
    read2_suffix: '_2.fq.gz'
  };
}

function analysisDefaults(settings: WebUISettings | null): AnalysisForm {
  return {
    feature_method: 'usearch-asv',
    chimera_mode: 'ref',
    reference_db: 'database/rdp_16s_v18.fa',
    annotation_database: 'rdp_16s_v18',
    otutab_method: 'usearch',
    filter_route: '16s',
    fastq_stripleft: 29,
    fastq_stripright: 18,
    fastq_maxee_rate: 0.01,
    feature_minsize: 10,
    feature_identity: 1,
    otutab_identity: 1,
    sintax_cutoff: 0.1,
    rarefaction_depth: 8000,
    rarefaction_seed: 1,
    threads: 1,
    beta_tree_path: '',
    command_timeout: '',
    color_palette: ''
  };
}

function isActiveJob(job: JobRecord | null): boolean {
  return Boolean(job && ['queued', 'checking', 'running'].includes(job.status));
}

function formatJobTime(value: string | null): string {
  if (!value) {
    return 'NA';
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function nonEmpty(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function jobCanShowLogs(job: JobRecord | null): boolean {
  return Boolean(job && ['completed', 'failed', 'cancelled'].includes(job.status));
}

function statusText(status: string, messages: Messages): string {
  const labels = messages.runMonitor.statusLabels as Record<string, string>;
  return labels[status] || status;
}

function JobPanel({
  title,
  job,
  logText,
  messages,
  onLoadLogs,
  onNavigate
}: {
  title: string;
  job: JobRecord | null;
  logText: string | null;
  messages: Messages;
  onLoadLogs: (job: JobRecord) => void;
  onNavigate: (page: PageId) => void;
}) {
  if (!job) {
    return null;
  }
  return (
    <section className="job-summary">
      <div className="job-summary-header">
        <div>
          <h3>{title}</h3>
          <p>{job.message || job.id}</p>
        </div>
        <StatusBadge status={job.status} label={statusText(job.status, messages)} />
      </div>
      <div className="summary-grid compact-grid">
        <div>
          <span>{messages.newAnalysis.jobId}</span>
          <code>{job.id}</code>
        </div>
        <div>
          <span>{messages.newAnalysis.startedAt}</span>
          <code>{formatJobTime(job.started_at)}</code>
        </div>
        <div>
          <span>{messages.newAnalysis.completedAt}</span>
          <code>{formatJobTime(job.completed_at)}</code>
        </div>
      </div>
      <label className="field">
        <span>{messages.newAnalysis.reproducibleCommand}</span>
        <textarea value={job.display_command} readOnly rows={2} />
      </label>
      <div className="inline-actions">
        <button type="button" onClick={() => onNavigate('runMonitor')}>
          {messages.newAnalysis.openRunMonitor}
        </button>
        <button type="button" onClick={() => onLoadLogs(job)} disabled={!jobCanShowLogs(job)}>
          {messages.newAnalysis.loadTechnicalLog}
        </button>
      </div>
      {logText ? <pre className="log-preview">{logText}</pre> : null}
    </section>
  );
}

export function NewAnalysis({
  settings,
  projectRoot,
  messages,
  onNavigate,
  onProjectSaved
}: NewAnalysisProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const [projectForm, setProjectForm] = useState<ProjectForm>(() => projectDefaults(settings, projectRoot, messages));
  const [inputForm, setInputForm] = useState<InputForm>(() => inputDefaults(settings));
  const [analysisForm, setAnalysisForm] = useState<AnalysisForm>(() => analysisDefaults(settings));
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [metadataResult, setMetadataResult] = useState<MetadataValidationResult | null>(null);
  const [pairPreview, setPairPreview] = useState<FastqPairingPreview | null>(null);
  const [paramsResult, setParamsResult] = useState<ParamsWriteResult | null>(null);
  const [databases, setDatabases] = useState<DatabaseRecord[]>([]);
  const [referenceGroup, setReferenceGroup] = useState('');
  const [comparisonCase, setComparisonCase] = useState('');
  const [comparisonControl, setComparisonControl] = useState('');
  const [comparisons, setComparisons] = useState<string[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preflightJob, setPreflightJob] = useState<JobRecord | null>(null);
  const [runJob, setRunJob] = useState<JobRecord | null>(null);
  const [jobLogs, setJobLogs] = useState<Record<string, string>>({});

  const currentStep = steps[stepIndex];
  const t = messages.newAnalysis;

  useEffect(() => {
    if (project) {
      return;
    }
    setProjectForm((current) => ({
      ...current,
      project_dir: current.project_dir || projectRoot || '',
      output_root: current.output_root || settings?.default_output_root || 'work'
    }));
    setInputForm((current) => ({
      ...current,
      metadata_path: current.metadata_path || settings?.default_metadata_path || 'metadata.txt',
      seq_dir: current.seq_dir || settings?.default_seq_dir || 'seq',
      sample_id_col: current.sample_id_col || settings?.default_sample_id_col || 'SampleID',
      group_col: current.group_col || settings?.default_group_col || 'Group'
    }));
  }, [project, projectRoot, settings]);

  useEffect(() => {
    let cancelled = false;
    async function loadDatabases() {
      try {
        const records = await api.listDatabases();
        if (!cancelled) {
          setDatabases(records);
        }
      } catch {
        if (!cancelled) {
          setDatabases([]);
        }
      }
    }
    void loadDatabases();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isActiveJob(preflightJob) && !isActiveJob(runJob)) {
      return;
    }

    const timer = window.setInterval(async () => {
      try {
        if (preflightJob && isActiveJob(preflightJob)) {
          setPreflightJob(await api.getJob(preflightJob.id));
        }
        if (runJob && isActiveJob(runJob)) {
          setRunJob(await api.getJob(runJob.id));
        }
      } catch {
        // Polling is best-effort; the explicit log button still exposes technical details.
      }
    }, 1800);

    return () => window.clearInterval(timer);
  }, [preflightJob, runJob]);

  const groupNames = useMemo(() => metadataResult?.groups.map((item) => item.group) || [], [metadataResult]);
  const selectedDatabase = databases.find((item) => item.name === analysisForm.annotation_database);

  function setProjectField<K extends keyof ProjectForm>(key: K, value: ProjectForm[K]) {
    setProjectForm((current) => ({ ...current, [key]: value }));
  }

  function setInputField<K extends keyof InputForm>(key: K, value: InputForm[K]) {
    setInputForm((current) => ({ ...current, [key]: value }));
    setParamsResult(null);
    if (key === 'metadata_path' || key === 'sample_id_col' || key === 'group_col') {
      setMetadataResult(null);
    }
    if (key === 'metadata_path' || key === 'seq_dir' || key === 'sample_id_col' || key === 'read1_suffix' || key === 'read2_suffix') {
      setPairPreview(null);
    }
  }

  function setAnalysisField<K extends keyof AnalysisForm>(key: K, value: AnalysisForm[K]) {
    setAnalysisForm((current) => ({ ...current, [key]: value }));
    setParamsResult(null);
  }

  async function createOrUpdateProject() {
    setBusy('project');
    setError(null);
    setNotice(null);
    try {
      const payload = {
        name: projectForm.name.trim(),
        project_dir: nonEmpty(projectForm.project_dir),
        output_root: projectForm.output_root.trim() || 'work',
        analysis_type: projectForm.analysis_type.trim() || '16S rRNA'
      };
      const saved = project
        ? await api.updateProject(project.id, payload)
        : await api.createProject({
            name: payload.name,
            project_dir: payload.project_dir,
            output_root: payload.output_root,
            analysis_type: payload.analysis_type
          });
      setProject(saved);
      onProjectSaved(saved);
      setNotice(t.projectSaved);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  async function validateMetadata() {
    if (!project) {
      return;
    }
    setBusy('metadata');
    setError(null);
    setNotice(null);
    try {
      const result = await api.validateMetadata(project.id, {
        metadata_path: inputForm.metadata_path,
        sample_id_col: inputForm.sample_id_col,
        group_col: inputForm.group_col
      });
      setMetadataResult(result);
      setNotice(result.status === 'failed' ? null : t.metadataChecked);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  async function previewPairs() {
    if (!project) {
      return;
    }
    setBusy('pairs');
    setError(null);
    setNotice(null);
    try {
      const result = await api.previewPairs(project.id, {
        metadata_path: inputForm.metadata_path,
        seq_dir: inputForm.seq_dir,
        sample_id_col: inputForm.sample_id_col,
        read1_suffix: inputForm.read1_suffix,
        read2_suffix: inputForm.read2_suffix
      });
      setPairPreview(result);
      setNotice(result.status === 'failed' ? null : t.pairsChecked);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  async function runInputChecks() {
    await validateMetadata();
    await previewPairs();
  }

  function addComparison() {
    if (!comparisonCase || !comparisonControl || comparisonCase === comparisonControl) {
      return;
    }
    const label = `${comparisonCase}:${comparisonControl}`;
    setComparisons((current) => (current.includes(label) ? current : [...current, label]));
    setComparisonCase('');
    setComparisonControl('');
  }

  function buildReferenceComparisons() {
    if (!referenceGroup) {
      return;
    }
    setComparisons(groupNames.filter((group) => group !== referenceGroup).map((group) => `${group}:${referenceGroup}`));
  }

  function selectDatabase(name: string) {
    const record = databases.find((item) => item.name === name);
    setAnalysisForm((current) => ({
      ...current,
      annotation_database: name,
      reference_db: record?.sequence_path || record?.path || current.reference_db
    }));
    setParamsResult(null);
  }

  function buildParamsDraft(): PipelineParamsDraft {
    const commandTimeout = analysisForm.command_timeout.trim();
    return {
      metadata_path: inputForm.metadata_path,
      seq_dir: inputForm.seq_dir,
      output_root: projectForm.output_root,
      read1_suffix: inputForm.read1_suffix,
      read2_suffix: inputForm.read2_suffix,
      fastq_stripleft: analysisForm.fastq_stripleft,
      fastq_stripright: analysisForm.fastq_stripright,
      fastq_maxee_rate: analysisForm.fastq_maxee_rate,
      feature_method: analysisForm.feature_method,
      feature_minsize: analysisForm.feature_minsize,
      feature_identity: analysisForm.feature_identity,
      chimera_mode: analysisForm.chimera_mode,
      reference_db: analysisForm.reference_db,
      otutab_method: analysisForm.otutab_method,
      otutab_identity: analysisForm.otutab_identity,
      annotation_database: analysisForm.annotation_database,
      sintax_cutoff: analysisForm.sintax_cutoff,
      filter_route: analysisForm.filter_route,
      beta_tree_path: nonEmpty(analysisForm.beta_tree_path),
      rarefaction_depth: analysisForm.rarefaction_depth,
      rarefaction_seed: analysisForm.rarefaction_seed,
      threads: analysisForm.threads,
      usearch_path: settings?.usearch_path || 'bin/usearch',
      vsearch_path: settings?.vsearch_path || 'bin/vsearch',
      command_timeout: commandTimeout ? Number(commandTimeout) : null,
      color_palette: nonEmpty(analysisForm.color_palette),
      differential: {
        group_col: inputForm.group_col,
        reference_group: nonEmpty(referenceGroup),
        comparisons,
        output_format: settings?.default_plot_format || 'html'
      }
    };
  }

  function validateAnalysisSettings(): string | null {
    if (analysisForm.fastq_stripleft < 0 || analysisForm.fastq_stripright < 0) {
      return t.invalidTrim;
    }
    if (analysisForm.fastq_maxee_rate <= 0) {
      return t.invalidMaxee;
    }
    if (analysisForm.feature_minsize < 1 || analysisForm.rarefaction_depth < 0 || analysisForm.threads < 1) {
      return t.invalidPositive;
    }
    if (analysisForm.feature_identity <= 0 || analysisForm.feature_identity > 1) {
      return t.invalidIdentity;
    }
    if (analysisForm.otutab_identity <= 0 || analysisForm.otutab_identity > 1) {
      return t.invalidIdentity;
    }
    if (analysisForm.sintax_cutoff < 0 || analysisForm.sintax_cutoff > 1) {
      return t.invalidCutoff;
    }
    if (analysisForm.command_timeout.trim() && Number.isNaN(Number(analysisForm.command_timeout))) {
      return t.invalidTimeout;
    }
    return null;
  }

  async function writeParams() {
    if (!project) {
      return;
    }
    const validationError = validateAnalysisSettings();
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusy('params');
    setError(null);
    setNotice(null);
    try {
      const result = await api.writeParams(project.id, buildParamsDraft());
      setParamsResult(result);
      setNotice(result.message);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  async function startPreflight() {
    if (!project) {
      return;
    }
    setBusy('preflight');
    setError(null);
    setNotice(null);
    try {
      if (!paramsResult) {
        const result = await api.writeParams(project.id, buildParamsDraft());
        setParamsResult(result);
      }
      const job = await api.startPreflight(project.id);
      setPreflightJob(job);
      setNotice(t.preflightStarted);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  async function startRun() {
    if (!project) {
      return;
    }
    setBusy('run');
    setError(null);
    setNotice(null);
    try {
      if (!paramsResult) {
        const result = await api.writeParams(project.id, buildParamsDraft());
        setParamsResult(result);
      }
      const job = await api.startRun(project.id);
      setRunJob(job);
      setNotice(t.runStarted);
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  async function loadJobLogs(job: JobRecord) {
    setBusy('logs');
    setError(null);
    try {
      const logs = await api.getJobLogs(job.id, 100);
      setJobLogs((current) => ({ ...current, [job.id]: logs.text || t.noLogYet }));
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setBusy(null);
    }
  }

  function canEnterStep(targetIndex: number): boolean {
    if (targetIndex <= stepIndex) {
      return true;
    }
    if (targetIndex >= 1 && !project) {
      return false;
    }
    if (targetIndex >= 2 && (!metadataResult || !pairPreview || metadataResult.status === 'failed' || pairPreview.status === 'failed')) {
      return false;
    }
    if (targetIndex >= 4 && Boolean(validateAnalysisSettings())) {
      return false;
    }
    return true;
  }

  function goNext() {
    if (canEnterStep(stepIndex + 1)) {
      setStepIndex((current) => Math.min(current + 1, steps.length - 1));
    }
  }

  function renderProjectStep() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{t.projectStep}</h2>
          {project ? <StatusBadge status="passed" label={t.created} /> : null}
        </div>
        <div className="form-grid two-columns">
          <label className="field">
            <span>{t.projectName}</span>
            <input value={projectForm.name} onChange={(event) => setProjectField('name', event.target.value)} />
          </label>
          <label className="field">
            <span>{t.analysisType}</span>
            <select
              value={projectForm.analysis_type}
              onChange={(event) => setProjectField('analysis_type', event.target.value)}
            >
              <option value="16S rRNA">16S rRNA</option>
            </select>
          </label>
          <label className="field">
            <span>{t.projectDir}</span>
            <input
              value={projectForm.project_dir}
              onChange={(event) => setProjectField('project_dir', event.target.value)}
              placeholder={projectRoot || '/path/to/X-Amplicon_mac'}
            />
            <small>{t.projectDirHelp}</small>
          </label>
          <label className="field">
            <span>{t.outputRoot}</span>
            <input value={projectForm.output_root} onChange={(event) => setProjectField('output_root', event.target.value)} />
          </label>
        </div>
        <div className="inline-actions">
          <button
            className="primary-button"
            type="button"
            onClick={createOrUpdateProject}
            disabled={!projectForm.name.trim() || busy === 'project'}
          >
            {project ? t.updateProject : t.createProject}
          </button>
          {project ? <code>{project.id}</code> : <span className="subtle-text">{t.createBeforeNext}</span>}
        </div>
      </section>
    );
  }

  function renderInputStep() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{t.inputStep}</h2>
          <div className="inline-actions">
            {metadataResult ? <StatusBadge status={metadataResult.status} label={metadataResult.status} /> : null}
            {pairPreview ? <StatusBadge status={pairPreview.status} label={pairPreview.status} /> : null}
          </div>
        </div>
        <div className="form-grid two-columns">
          <label className="field">
            <span>{t.metadataPath}</span>
            <input value={inputForm.metadata_path} onChange={(event) => setInputField('metadata_path', event.target.value)} />
          </label>
          <label className="field">
            <span>{t.seqDir}</span>
            <input value={inputForm.seq_dir} onChange={(event) => setInputField('seq_dir', event.target.value)} />
          </label>
          <label className="field">
            <span>{t.sampleIdCol}</span>
            <input value={inputForm.sample_id_col} onChange={(event) => setInputField('sample_id_col', event.target.value)} />
          </label>
          <label className="field">
            <span>{t.groupCol}</span>
            <input value={inputForm.group_col} onChange={(event) => setInputField('group_col', event.target.value)} />
          </label>
          <label className="field">
            <span>{t.read1Suffix}</span>
            <input list="read1-suffixes" value={inputForm.read1_suffix} onChange={(event) => setInputField('read1_suffix', event.target.value)} />
            <datalist id="read1-suffixes">
              {readSuffixOptions.map((item) => <option key={item} value={item} />)}
            </datalist>
          </label>
          <label className="field">
            <span>{t.read2Suffix}</span>
            <input list="read2-suffixes" value={inputForm.read2_suffix} onChange={(event) => setInputField('read2_suffix', event.target.value)} />
            <datalist id="read2-suffixes">
              {read2SuffixOptions.map((item) => <option key={item} value={item} />)}
            </datalist>
          </label>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={validateMetadata} disabled={!project || busy === 'metadata'}>
            {t.validateMetadata}
          </button>
          <button type="button" onClick={previewPairs} disabled={!project || busy === 'pairs'}>
            {t.previewPairs}
          </button>
          <button className="primary-button" type="button" onClick={runInputChecks} disabled={!project || Boolean(busy)}>
            {t.runBothChecks}
          </button>
        </div>

        <div className="section-grid two-columns result-panels">
          {metadataResult ? (
            <section className="soft-panel">
              <h3>{t.metadataSummary}</h3>
              <div className="summary-grid compact-grid">
                <div><span>{t.samples}</span><strong>{metadataResult.sample_count}</strong></div>
                <div><span>{t.rows}</span><strong>{metadataResult.rows}</strong></div>
                <div><span>{t.columns}</span><strong>{metadataResult.columns}</strong></div>
                <div><span>{t.groups}</span><strong>{metadataResult.groups.length}</strong></div>
              </div>
              {metadataResult.messages.length ? <ul className="message-list">{metadataResult.messages.map((item) => <li key={item}>{item}</li>)}</ul> : null}
              {metadataResult.suggestions.length ? <ul className="suggestion-list">{metadataResult.suggestions.map((item) => <li key={item}>{item}</li>)}</ul> : null}
            </section>
          ) : null}

          {pairPreview ? (
            <section className="soft-panel">
              <h3>{t.pairingSummary}</h3>
              <div className="summary-grid compact-grid">
                <div><span>{t.samples}</span><strong>{pairPreview.sample_count}</strong></div>
                <div><span>{t.matchedPairs}</span><strong>{pairPreview.matched_pairs}</strong></div>
                <div><span>{t.missingR1}</span><strong>{pairPreview.missing_read1.length}</strong></div>
                <div><span>{t.missingR2}</span><strong>{pairPreview.missing_read2.length}</strong></div>
              </div>
              {pairPreview.missing_read1.length || pairPreview.missing_read2.length || pairPreview.extra_fastq_files.length ? (
                <div className="warning-block">
                  <strong>{t.unmatchedFiles}</strong>
                  <p>{[...pairPreview.missing_read1, ...pairPreview.missing_read2, ...pairPreview.extra_fastq_files].slice(0, 12).join(', ')}</p>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      </section>
    );
  }

  function renderGroupsStep() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{t.groupsStep}</h2>
          <button type="button" onClick={validateMetadata} disabled={!project || busy === 'metadata'}>
            {t.refreshGroups}
          </button>
        </div>
        <div className="form-grid two-columns">
          <label className="field">
            <span>{t.groupColumn}</span>
            <select value={inputForm.group_col} onChange={(event) => setInputField('group_col', event.target.value)}>
              {(metadataResult?.column_names.length ? metadataResult.column_names : [inputForm.group_col]).map((column) => (
                <option key={column} value={column}>{column}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>{t.referenceGroup}</span>
            <select value={referenceGroup} onChange={(event) => setReferenceGroup(event.target.value)}>
              <option value="">{t.noReference}</option>
              {groupNames.map((group) => <option key={group} value={group}>{group}</option>)}
            </select>
          </label>
        </div>

        {metadataResult ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t.group}</th>
                  <th>{t.sampleCount}</th>
                  <th>{t.sampleIds}</th>
                  <th>{t.status}</th>
                </tr>
              </thead>
              <tbody>
                {metadataResult.groups.map((group) => (
                  <tr key={group.group}>
                    <td><strong>{group.group}</strong></td>
                    <td>{group.count}</td>
                    <td>{group.samples.slice(0, 8).join(', ')}{group.samples.length > 8 ? ' ...' : ''}</td>
                    <td>
                      <StatusBadge
                        status={group.count < 2 ? 'warning' : 'passed'}
                        label={group.count < 2 ? t.lowSampleWarning : t.ready}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state compact"><p>{t.validateMetadataFirst}</p></div>
        )}

        <section className="soft-panel">
          <h3>{t.comparisonPlan}</h3>
          <p className="subtle-text">{t.comparisonDirectionHelp}</p>
          <div className="form-grid three-columns">
            <label className="field">
              <span>{t.caseGroup}</span>
              <select value={comparisonCase} onChange={(event) => setComparisonCase(event.target.value)}>
                <option value="">{t.selectGroup}</option>
                {groupNames.map((group) => <option key={group} value={group}>{group}</option>)}
              </select>
            </label>
            <label className="field">
              <span>{t.controlGroup}</span>
              <select value={comparisonControl} onChange={(event) => setComparisonControl(event.target.value)}>
                <option value="">{t.selectGroup}</option>
                {groupNames.map((group) => <option key={group} value={group}>{group}</option>)}
              </select>
            </label>
            <div className="field action-field">
              <span>{t.actions}</span>
              <button type="button" onClick={addComparison} disabled={!comparisonCase || !comparisonControl || comparisonCase === comparisonControl}>
                {t.addComparison}
              </button>
            </div>
          </div>
          <div className="inline-actions">
            <button type="button" onClick={buildReferenceComparisons} disabled={!referenceGroup || groupNames.length < 2}>
              {t.generateFromReference}
            </button>
            <button type="button" onClick={() => setComparisons([])} disabled={!comparisons.length}>
              {t.clearComparisons}
            </button>
          </div>
          {comparisons.length ? (
            <div className="comparison-list">
              {comparisons.map((comparison) => (
                <span className="comparison-chip" key={comparison}>
                  {comparison}
                  <button type="button" aria-label={`${t.removeComparison} ${comparison}`} onClick={() => setComparisons((current) => current.filter((item) => item !== comparison))}>
                    x
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="subtle-text">{t.noComparisons}</p>
          )}
        </section>
      </section>
    );
  }

  function renderAnalysisStep() {
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{t.analysisStep}</h2>
          <button type="button" onClick={() => setShowAdvanced((current) => !current)}>
            {showAdvanced ? t.hideAdvanced : t.showAdvanced}
          </button>
        </div>
        {validateAnalysisSettings() ? <div className="alert alert-error">{validateAnalysisSettings()}</div> : null}
        <div className="form-grid three-columns">
          <label className="field">
            <span>{t.featureMethod}</span>
            <select value={analysisForm.feature_method} onChange={(event) => setAnalysisField('feature_method', event.target.value as AnalysisForm['feature_method'])}>
              <option value="usearch-asv">usearch-asv</option>
              <option value="usearch-otu">usearch-otu</option>
              <option value="vsearch-otu">vsearch-otu</option>
            </select>
          </label>
          <label className="field">
            <span>{t.taxonomyDatabase}</span>
            <select value={analysisForm.annotation_database} onChange={(event) => selectDatabase(event.target.value)}>
              <option value={analysisForm.annotation_database}>{analysisForm.annotation_database}</option>
              {databases.filter((item) => item.name !== analysisForm.annotation_database).map((record) => (
                <option key={record.name} value={record.name}>
                  {record.name}{record.exists === false ? ` (${t.missing})` : ''}
                </option>
              ))}
            </select>
            {selectedDatabase ? <small>{selectedDatabase.sequence_path || selectedDatabase.path}</small> : null}
          </label>
          <label className="field">
            <span>{t.chimeraMode}</span>
            <select value={analysisForm.chimera_mode} onChange={(event) => setAnalysisField('chimera_mode', event.target.value as AnalysisForm['chimera_mode'])}>
              <option value="ref">ref</option>
              <option value="none">none</option>
            </select>
          </label>
          <label className="field">
            <span>{t.filterRoute}</span>
            <select value={analysisForm.filter_route} onChange={(event) => setAnalysisField('filter_route', event.target.value as AnalysisForm['filter_route'])}>
              <option value="16s">16s</option>
              <option value="its">its</option>
              <option value="none">none</option>
            </select>
          </label>
          <label className="field">
            <span>{t.rarefactionDepth}</span>
            <input type="number" min={0} value={analysisForm.rarefaction_depth} onChange={(event) => setAnalysisField('rarefaction_depth', Number(event.target.value))} />
          </label>
          <label className="field">
            <span>{t.threads}</span>
            <input type="number" min={1} value={analysisForm.threads} onChange={(event) => setAnalysisField('threads', Number(event.target.value))} />
          </label>
        </div>

        {showAdvanced ? (
          <div className="form-grid three-columns advanced-grid">
            <label className="field">
              <span>{t.referenceDb}</span>
              <input value={analysisForm.reference_db} onChange={(event) => setAnalysisField('reference_db', event.target.value)} />
            </label>
            <label className="field">
              <span>{t.otutabMethod}</span>
              <select value={analysisForm.otutab_method} onChange={(event) => setAnalysisField('otutab_method', event.target.value as AnalysisForm['otutab_method'])}>
                <option value="usearch">usearch</option>
                <option value="vsearch">vsearch</option>
              </select>
            </label>
            <label className="field">
              <span>{t.fastqStripLeft}</span>
              <input type="number" min={0} value={analysisForm.fastq_stripleft} onChange={(event) => setAnalysisField('fastq_stripleft', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.fastqStripRight}</span>
              <input type="number" min={0} value={analysisForm.fastq_stripright} onChange={(event) => setAnalysisField('fastq_stripright', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.fastqMaxeeRate}</span>
              <input type="number" min={0.0001} step={0.001} value={analysisForm.fastq_maxee_rate} onChange={(event) => setAnalysisField('fastq_maxee_rate', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.featureMinsize}</span>
              <input type="number" min={1} value={analysisForm.feature_minsize} onChange={(event) => setAnalysisField('feature_minsize', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.featureIdentity}</span>
              <input type="number" min={0.01} max={1} step={0.01} value={analysisForm.feature_identity} onChange={(event) => setAnalysisField('feature_identity', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.otutabIdentity}</span>
              <input type="number" min={0.01} max={1} step={0.01} value={analysisForm.otutab_identity} onChange={(event) => setAnalysisField('otutab_identity', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.sintaxCutoff}</span>
              <input type="number" min={0} max={1} step={0.01} value={analysisForm.sintax_cutoff} onChange={(event) => setAnalysisField('sintax_cutoff', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.rarefactionSeed}</span>
              <input type="number" min={0} value={analysisForm.rarefaction_seed} onChange={(event) => setAnalysisField('rarefaction_seed', Number(event.target.value))} />
            </label>
            <label className="field">
              <span>{t.betaTreePath}</span>
              <input value={analysisForm.beta_tree_path} onChange={(event) => setAnalysisField('beta_tree_path', event.target.value)} />
            </label>
            <label className="field">
              <span>{t.commandTimeout}</span>
              <input value={analysisForm.command_timeout} onChange={(event) => setAnalysisField('command_timeout', event.target.value)} placeholder={messages.auto} />
            </label>
            <label className="field wide-field">
              <span>{t.colorPalette}</span>
              <input value={analysisForm.color_palette} onChange={(event) => setAnalysisField('color_palette', event.target.value)} placeholder="#2f6f73,#d8903f,#6b8f71" />
            </label>
          </div>
        ) : null}
      </section>
    );
  }

  function renderRunStep() {
    const preflightPassed = preflightJob?.status === 'completed';
    return (
      <section className="panel">
        <div className="panel-header">
          <h2>{t.runStep}</h2>
          {paramsResult ? <StatusBadge status={paramsResult.status} label={statusText(paramsResult.status, messages)} /> : null}
        </div>
        <div className="summary-grid">
          <div><span>{t.projectName}</span><strong>{project?.name || projectForm.name}</strong></div>
          <div><span>{t.projectDir}</span><code>{project?.project_dir || projectForm.project_dir}</code></div>
          <div><span>{t.metadataPath}</span><code>{inputForm.metadata_path}</code></div>
          <div><span>{t.seqDir}</span><code>{inputForm.seq_dir}</code></div>
          <div><span>{t.samples}</span><strong>{metadataResult?.sample_count ?? 'NA'}</strong></div>
          <div><span>{t.matchedPairs}</span><strong>{pairPreview ? `${pairPreview.matched_pairs}/${pairPreview.sample_count}` : 'NA'}</strong></div>
          <div><span>{t.featureMethod}</span><strong>{analysisForm.feature_method}</strong></div>
          <div><span>{t.taxonomyDatabase}</span><strong>{analysisForm.annotation_database}</strong></div>
          <div><span>{t.comparisonPlan}</span><strong>{comparisons.length ? comparisons.join(', ') : t.noComparisons}</strong></div>
        </div>
        {paramsResult ? (
          <div className="alert alert-success">
            {t.paramsWritten}: <code>{paramsResult.params_path}</code>
          </div>
        ) : null}
        <div className="inline-actions">
          <button type="button" onClick={writeParams} disabled={!project || Boolean(validateAnalysisSettings()) || busy === 'params'}>
            {t.writeParams}
          </button>
          <button className="primary-button" type="button" onClick={startPreflight} disabled={!project || Boolean(validateAnalysisSettings()) || busy === 'preflight'}>
            {t.runPreflight}
          </button>
          <button type="button" onClick={startRun} disabled={!project || !preflightPassed || busy === 'run'}>
            {t.startFullRun}
          </button>
        </div>
        {preflightJob?.status === 'failed' ? (
          <div className="alert alert-error">
            {t.preflightFailedHelp}
          </div>
        ) : null}
        <JobPanel
          title={t.preflightJob}
          job={preflightJob}
          logText={preflightJob ? jobLogs[preflightJob.id] || null : null}
          messages={messages}
          onLoadLogs={loadJobLogs}
          onNavigate={onNavigate}
        />
        <JobPanel
          title={t.runJob}
          job={runJob}
          logText={runJob ? jobLogs[runJob.id] || null : null}
          messages={messages}
          onLoadLogs={loadJobLogs}
          onNavigate={onNavigate}
        />
      </section>
    );
  }

  return (
    <section className="page">
      <div className="page-header">
        <div>
          <h1>{t.title}</h1>
          <p>{t.subtitle}</p>
        </div>
      </div>

      {notice ? <div className="alert alert-success">{notice}</div> : null}
      {error ? <div className="alert alert-error">{error}</div> : null}

      <div className="wizard-steps" aria-label={t.stepsAria}>
        {steps.map((step, index) => (
          <button
            key={step}
            type="button"
            className={`wizard-step${index === stepIndex ? ' active' : ''}${canEnterStep(index) ? '' : ' disabled'}`}
            onClick={() => canEnterStep(index) && setStepIndex(index)}
          >
            <span>{index + 1}</span>
            {t.stepLabels[step]}
          </button>
        ))}
      </div>

      {currentStep === 'project' ? renderProjectStep() : null}
      {currentStep === 'inputs' ? renderInputStep() : null}
      {currentStep === 'groups' ? renderGroupsStep() : null}
      {currentStep === 'analysis' ? renderAnalysisStep() : null}
      {currentStep === 'run' ? renderRunStep() : null}

      <div className="wizard-footer">
        <button type="button" onClick={() => setStepIndex((current) => Math.max(0, current - 1))} disabled={stepIndex === 0}>
          {t.back}
        </button>
        <button className="primary-button" type="button" onClick={goNext} disabled={stepIndex === steps.length - 1 || !canEnterStep(stepIndex + 1)}>
          {t.next}
        </button>
      </div>
    </section>
  );
}
