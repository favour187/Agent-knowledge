import { useState, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Plus, Upload, Play, Cpu, HardDrive, Zap, Clock,
  CheckCircle2, XCircle, Loader2, ChevronDown, ChevronRight,
  Gauge, BrainCircuit, FileText, Database,
} from 'lucide-react'
import { trainingApi } from '../api/training'
import { apiErrorMessage } from '../api/client'
import {
  StatusBadge, SkeletonTable, SkeletonCards, EmptyState,
  ErrorBanner, Modal, ConfirmButton, Spinner,
} from '../components/ui/Primitives'

/* ================================================================
   Tab system
   ================================================================ */

const TABS = [
  { id: 'train', label: 'Train', icon: Zap },
  { id: 'datasets', label: 'Datasets', icon: Database },
  { id: 'runs', label: 'Training runs', icon: Clock },
  { id: 'adapters', label: 'Adapters', icon: BrainCircuit },
]

/* ================================================================
   Main page
   ================================================================ */

export default function TrainingPage() {
  const [tab, setTab] = useState('train')

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Model Training</h1>
          <p className="page-subtitle">
            Fine-tune adapters (LoRA / QLoRA) on top of base models using your own data.
          </p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="toolbar" style={{ marginBottom: 20 }}>
        {TABS.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.id}
              className={`btn btn-sm${tab === t.id ? ' btn-primary' : ''}`}
              onClick={() => setTab(t.id)}
              style={tab !== t.id ? { background: 'transparent', border: '1px solid var(--border-soft)' } : undefined}
            >
              <Icon size={14} />
              {t.label}
            </button>
          )
        })}
      </div>

      {tab === 'train' && <TrainTab />}
      {tab === 'datasets' && <DatasetsTab />}
      {tab === 'runs' && <RunsTab />}
      {tab === 'adapters' && <AdaptersTab />}
    </div>
  )
}

/* ================================================================
   Train Tab — configuration + start
   ================================================================ */

function TrainTab() {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    base_model: 'gpt2',
    dataset_path: '',
    strategy: 'lora',
    epochs: 3,
    batch_size: 4,
    learning_rate: 3e-4,
    lora_r: 16,
    lora_alpha: 32,
    lora_dropout: 0.05,
    max_seq_length: 2048,
    gradient_accumulation_steps: 4,
    warmup_ratio: 0.03,
    weight_decay: 0.01,
    lr_scheduler_type: 'cosine',
  })
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [estimateResult, setEstimateResult] = useState(null)

  const { data: datasets } = useQuery({
    queryKey: ['training', 'datasets'],
    queryFn: trainingApi.listDatasets,
  })

  const startMutation = useMutation({
    mutationFn: (dryRun) =>
      dryRun ? trainingApi.dryRun(form) : trainingApi.startTraining(form),
    onSuccess: (result, dryRun) => {
      qc.invalidateQueries({ queryKey: ['training', 'runs'] })
      qc.invalidateQueries({ queryKey: ['training', 'adapters'] })
      if (dryRun) {
        toast.success('Dry run passed — configuration is valid')
      } else {
        toast.success(`Training ${result.status}`)
      }
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  const estimateMutation = useMutation({
    mutationFn: () => trainingApi.estimateMemory({
      model_size_b: 0.12,  // GPT-2 small is ~124M
      batch_size: form.batch_size,
      seq_length: form.max_seq_length,
      strategy: form.strategy,
      rank: form.lora_r,
    }),
    onSuccess: (data) => setEstimateResult(data),
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>
      {/* Config form */}
      <div className="card">
        <h3 style={{ fontSize: 15, marginBottom: 18, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Zap size={16} style={{ color: 'var(--amber)' }} />
          Training Configuration
        </h3>

        <div className="field">
          <label>Base model</label>
          <input
            className="input mono"
            value={form.base_model}
            onChange={(e) => setForm({ ...form, base_model: e.target.value })}
            placeholder="gpt2"
          />
          <span className="field-hint">HuggingFace model name or local path</span>
        </div>

        <div className="field">
          <label>Dataset</label>
          <select
            className="select"
            value={form.dataset_path}
            onChange={(e) => setForm({ ...form, dataset_path: e.target.value })}
          >
            <option value="">Auto-detect latest upload</option>
            {datasets?.map((d) => (
              <option key={d.path} value={d.path}>
                {d.name} ({d.samples} samples)
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div className="field">
            <label>Strategy</label>
            <select
              className="select"
              value={form.strategy}
              onChange={(e) => setForm({ ...form, strategy: e.target.value })}
            >
              <option value="lora">LoRA</option>
              <option value="qlora">QLoRA (4-bit)</option>
              <option value="full">Full fine-tune</option>
            </select>
          </div>

          <div className="field">
            <label>Epochs</label>
            <input
              className="input"
              type="number"
              min={1}
              max={100}
              value={form.epochs}
              onChange={(e) => setForm({ ...form, epochs: Number(e.target.value) })}
            />
          </div>

          <div className="field">
            <label>Batch size</label>
            <input
              className="input"
              type="number"
              min={1}
              max={64}
              value={form.batch_size}
              onChange={(e) => setForm({ ...form, batch_size: Number(e.target.value) })}
            />
          </div>

          <div className="field">
            <label>Learning rate</label>
            <input
              className="input mono"
              type="number"
              step="0.0001"
              value={form.learning_rate}
              onChange={(e) => setForm({ ...form, learning_rate: Number(e.target.value) })}
            />
          </div>
        </div>

        {/* LoRA-specific */}
        {form.strategy !== 'full' && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
              <div className="field">
                <label>LoRA rank (r)</label>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={256}
                  value={form.lora_r}
                  onChange={(e) => setForm({ ...form, lora_r: Number(e.target.value) })}
                />
              </div>
              <div className="field">
                <label>LoRA alpha</label>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={512}
                  value={form.lora_alpha}
                  onChange={(e) => setForm({ ...form, lora_alpha: Number(e.target.value) })}
                />
              </div>
              <div className="field">
                <label>LoRA dropout</label>
                <input
                  className="input"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={form.lora_dropout}
                  onChange={(e) => setForm({ ...form, lora_dropout: Number(e.target.value) })}
                />
              </div>
            </div>
          </>
        )}

        {/* Advanced toggle */}
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => setShowAdvanced(!showAdvanced)}
          style={{ marginTop: 8, marginBottom: showAdvanced ? 12 : 0 }}
        >
          {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Advanced settings
        </button>

        {showAdvanced && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div className="field">
              <label>Max sequence length</label>
              <input
                className="input"
                type="number"
                min={32}
                max={8192}
                value={form.max_seq_length}
                onChange={(e) => setForm({ ...form, max_seq_length: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Gradient accumulation</label>
              <input
                className="input"
                type="number"
                min={1}
                max={64}
                value={form.gradient_accumulation_steps}
                onChange={(e) => setForm({ ...form, gradient_accumulation_steps: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Warmup ratio</label>
              <input
                className="input"
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={form.warmup_ratio}
                onChange={(e) => setForm({ ...form, warmup_ratio: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Weight decay</label>
              <input
                className="input"
                type="number"
                min={0}
                max={1}
                step={0.001}
                value={form.weight_decay}
                onChange={(e) => setForm({ ...form, weight_decay: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>LR scheduler</label>
              <select
                className="select"
                value={form.lr_scheduler_type}
                onChange={(e) => setForm({ ...form, lr_scheduler_type: e.target.value })}
              >
                <option value="cosine">Cosine</option>
                <option value="linear">Linear</option>
                <option value="constant">Constant</option>
                <option value="constant_with_warmup">Constant with warmup</option>
              </select>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex-row" style={{ marginTop: 20, gap: 8 }}>
          <button
            className="btn btn-primary"
            onClick={() => startMutation.mutate(false)}
            disabled={startMutation.isPending}
            style={{ flex: 1, justifyContent: 'center' }}
          >
            {startMutation.isPending ? <Spinner /> : <Play size={14} />}
            {startMutation.isPending ? 'Training…' : 'Start training'}
          </button>
          <button
            className="btn"
            onClick={() => startMutation.mutate(true)}
            disabled={startMutation.isPending}
            title="Validate config without training"
          >
            <CheckCircle2 size={14} /> Dry run
          </button>
          <button
            className="btn"
            onClick={() => estimateMutation.mutate()}
            disabled={estimateMutation.isPending}
            title="Estimate VRAM requirements"
          >
            <HardDrive size={14} /> Estimate
          </button>
        </div>

        {startMutation.isError && (
          <ErrorBanner message={apiErrorMessage(startMutation.error)} />
        )}
      </div>

      {/* Right sidebar: estimates + recent runs */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Memory estimate */}
        {estimateResult && (
          <div className="card">
            <h3 style={{ fontSize: 13, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <HardDrive size={14} style={{ color: 'var(--violet)' }} />
              Memory Estimate
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {Object.entries(estimateResult.estimate || {}).map(([key, val]) => (
                typeof val === 'number' ? (
                  <div key={key} className="flex-between" style={{ fontSize: 12 }}>
                    <span className="text-muted">{key.replace(/_/g, ' ')}</span>
                    <span className="mono">{val.toFixed(2)} GB</span>
                  </div>
                ) : null
              ))}
            </div>
            {estimateResult.estimate?.recommendation && (
              <p className="text-muted" style={{ fontSize: 11, marginTop: 10, lineHeight: 1.4 }}>
                {estimateResult.estimate.recommendation}
              </p>
            )}
          </div>
        )}

        {/* Quick info */}
        <div className="card">
          <h3 style={{ fontSize: 13, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Gauge size={14} style={{ color: 'var(--teal)' }} />
            Strategy Guide
          </h3>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            {form.strategy === 'lora' && (
              <p>LoRA trains ~0.1–1% of model parameters via low-rank adapters. Fast, memory-efficient, ideal for most use cases.</p>
            )}
            {form.strategy === 'qlora' && (
              <p>QLoRA quantizes the base model to 4-bit before applying LoRA. Trains 7B models on ~8GB VRAM. Slightly slower.</p>
            )}
            {form.strategy === 'full' && (
              <p>Full fine-tuning updates all parameters. Highest quality but requires significant VRAM. Only for small models.</p>
            )}
          </div>
          <div className="divider" />
          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>
            <p>LoRA rank {form.lora_r} · α {form.lora_alpha} · dropout {form.lora_dropout}</p>
            <p style={{ marginTop: 4 }}>Effective scaling: α/r = {(form.lora_alpha / form.lora_r).toFixed(1)}</p>
          </div>
        </div>

        {/* Recent runs quick view */}
        <RecentRunsCard />
      </div>
    </div>
  )
}

function RecentRunsCard() {
  const { data: runs } = useQuery({
    queryKey: ['training', 'runs'],
    queryFn: trainingApi.listRuns,
    staleTime: 10_000,
  })

  if (!runs || runs.length === 0) return null

  return (
    <div className="card">
      <h3 style={{ fontSize: 13, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
        <Clock size={14} style={{ color: 'var(--amber)' }} />
        Recent Runs
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {runs.slice(0, 5).map((run) => (
          <div key={run.run_id} className="flex-between" style={{ fontSize: 12, padding: '6px 0', borderBottom: '1px solid var(--border-soft)' }}>
            <div>
              <span className="mono" style={{ color: 'var(--text-primary)' }}>{run.run_id}</span>
              <span className="text-muted" style={{ marginLeft: 8 }}>{run.strategy}</span>
            </div>
            <RunStatusBadge status={run.status} />
          </div>
        ))}
      </div>
    </div>
  )
}

/* ================================================================
   Datasets Tab
   ================================================================ */

function DatasetsTab() {
  const qc = useQueryClient()
  const fileRef = useRef(null)
  const [previewDataset, setPreviewDataset] = useState(null)

  const { data: datasets, isLoading } = useQuery({
    queryKey: ['training', 'datasets'],
    queryFn: trainingApi.listDatasets,
  })

  const uploadMutation = useMutation({
    mutationFn: (file) => trainingApi.uploadDataset(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['training', 'datasets'] })
      toast.success(`Uploaded ${data.name} (${data.samples} samples)`)
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (file) uploadMutation.mutate(file)
    e.target.value = ''
  }

  return (
    <div>
      <div className="flex-row" style={{ marginBottom: 16, gap: 8 }}>
        <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={uploadMutation.isPending}>
          {uploadMutation.isPending ? <Spinner /> : <Upload size={14} />}
          Upload dataset
        </button>
        <input ref={fileRef} type="file" accept=".jsonl,.json,.csv" style={{ display: 'none' }} onChange={handleFileChange} />
        <span className="text-muted" style={{ fontSize: 12 }}>Supports .jsonl, .json, .csv</span>
      </div>

      {isLoading && <SkeletonTable rows={3} cols={5} />}

      {datasets && datasets.length === 0 && (
        <EmptyState
          title="No datasets uploaded"
          hint="Upload a JSONL, JSON, or CSV file to use as training data."
          icon={Database}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => fileRef.current?.click()}>
              <Upload size={14} /> Upload dataset
            </button>
          }
        />
      )}

      {datasets && datasets.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Format</th>
                <th>Samples</th>
                <th>Size</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((d) => (
                <tr key={d.path}>
                  <td>
                    <div className="flex-row gap-sm">
                      <FileText size={14} style={{ color: 'var(--amber)', opacity: 0.7 }} />
                      <span style={{ fontWeight: 500 }}>{d.name}</span>
                    </div>
                  </td>
                  <td className="mono text-muted">{d.format}</td>
                  <td className="mono text-muted">{d.samples >= 0 ? d.samples : 'parse error'}</td>
                  <td className="text-muted">{formatBytes(d.size_bytes)}</td>
                  <td>
                    <button className="btn btn-ghost btn-sm" onClick={() => setPreviewDataset(d)}>
                      Preview
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {previewDataset && (
        <Modal title={`Preview: ${previewDataset.name}`} onClose={() => setPreviewDataset(null)} width={600}>
          <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
            {previewDataset.samples} samples · {previewDataset.format} · {formatBytes(previewDataset.size_bytes)}
          </p>
          {previewDataset.preview?.map((item, i) => (
            <div key={i} className="card" style={{ marginBottom: 8, padding: 12, background: 'var(--bg-canvas)' }}>
              <pre className="mono" style={{ margin: 0, fontSize: 11.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {JSON.stringify(item, null, 2)}
              </pre>
            </div>
          ))}
        </Modal>
      )}
    </div>
  )
}

/* ================================================================
   Runs Tab
   ================================================================ */

function RunsTab() {
  const { data: runs, isLoading, error } = useQuery({
    queryKey: ['training', 'runs'],
    queryFn: trainingApi.listRuns,
    refetchInterval: (data) => {
      // Auto-refresh if any run is still running
      const hasRunning = data?.some((r) => r.status === 'running')
      return hasRunning ? 3000 : false
    },
  })

  const [expanded, setExpanded] = useState(null)

  return (
    <div>
      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonTable rows={4} cols={6} />}

      {runs && runs.length === 0 && (
        <EmptyState
          title="No training runs yet"
          hint="Start a training run from the Train tab."
          icon={Zap}
        />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {runs?.map((run) => (
          <div key={run.run_id} className="card">
            <div
              className="flex-between"
              style={{ cursor: 'pointer' }}
              onClick={() => setExpanded(expanded === run.run_id ? null : run.run_id)}
            >
              <div className="flex-row gap-md">
                {expanded === run.run_id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                <div>
                  <div className="flex-row gap-sm">
                    <span className="mono" style={{ fontWeight: 500 }}>{run.run_id}</span>
                    <RunStatusBadge status={run.status} />
                  </div>
                  <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
                    {run.base_model} · {run.strategy} · {run.dataset_path?.split('/').pop()}
                  </div>
                </div>
              </div>
              <div style={{ textAlign: 'right', fontSize: 12 }}>
                {run.duration_seconds != null && (
                  <div className="mono text-muted">{run.duration_seconds.toFixed(1)}s</div>
                )}
                {run.final_loss != null && (
                  <div className="mono" style={{ color: 'var(--teal)' }}>loss: {run.final_loss.toFixed(4)}</div>
                )}
              </div>
            </div>

            {expanded === run.run_id && (
              <div style={{ marginTop: 16, paddingLeft: 24 }}>
                {/* Config */}
                <h4 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Configuration
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8, marginBottom: 16 }}>
                  {Object.entries(run.config || {}).slice(0, 12).map(([key, val]) => (
                    <div key={key} style={{ fontSize: 12 }}>
                      <span className="text-muted">{key}: </span>
                      <span className="mono">{typeof val === 'number' ? val : String(val).slice(0, 40)}</span>
                    </div>
                  ))}
                </div>

                {/* Stages */}
                {Object.keys(run.stages || {}).length > 0 && (
                  <>
                    <h4 style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      Pipeline Stages
                    </h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {Object.entries(run.stages).map(([stage, info]) => (
                        <div key={stage} className="flex-between" style={{ padding: '8px 12px', background: 'var(--bg-canvas)', borderRadius: 'var(--radius-md)', fontSize: 12 }}>
                          <span style={{ textTransform: 'capitalize' }}>{stage.replace(/_/g, ' ')}</span>
                          <div className="flex-row gap-sm">
                            {info.status && (
                              <span className={`badge ${info.status === 'completed' ? 'status-completed' : 'status-failed'}`}>
                                <span className="badge-dot" />
                                {info.status}
                              </span>
                            )}
                            {info.train_samples != null && (
                              <span className="mono text-muted">{info.train_samples} samples</span>
                            )}
                            {info.final_loss != null && (
                              <span className="mono" style={{ color: 'var(--teal)' }}>loss: {info.final_loss}</span>
                            )}
                            {info.duration != null && (
                              <span className="mono text-muted">{info.duration}s</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {run.error && (
                  <div className="error-banner" style={{ marginTop: 12 }}>
                    {run.error}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ================================================================
   Adapters Tab
   ================================================================ */

function AdaptersTab() {
  const { data: adapters, isLoading, error } = useQuery({
    queryKey: ['training', 'adapters'],
    queryFn: trainingApi.listAdapters,
  })

  return (
    <div>
      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonCards count={4} />}

      {adapters && adapters.length === 0 && (
        <EmptyState
          title="No adapters trained yet"
          hint="Complete a training run to produce an adapter."
          icon={BrainCircuit}
        />
      )}

      {adapters && adapters.length > 0 && (
        <div className="grid-cards">
          {adapters.map((a) => (
            <div key={a.name} className="card">
              <div className="flex-between">
                <span className="badge">{a.strategy}</span>
                <span className="mono text-muted" style={{ fontSize: 11 }}>r={a.rank}</span>
              </div>
              <h3 className="mono" style={{ fontSize: 14, marginTop: 10 }}>{a.name}</h3>
              <p className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                {a.base_model} · α={a.alpha}
              </p>
              {a.path && (
                <p className="mono text-muted" style={{ fontSize: 10, marginTop: 6, wordBreak: 'break-all' }}>
                  {a.path}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ================================================================
   Helpers
   ================================================================ */

function RunStatusBadge({ status }) {
  const map = {
    running: { color: 'var(--amber)', icon: Loader2, spin: true },
    completed: { color: 'var(--teal)', icon: CheckCircle2 },
    dry_run_completed: { color: 'var(--teal)', icon: CheckCircle2 },
    failed: { color: 'var(--danger)', icon: XCircle },
  }
  const cfg = map[status] || map.running
  const Icon = cfg.icon

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      fontSize: 11,
      color: cfg.color,
      fontWeight: 500,
    }}>
      <Icon size={12} className={cfg.spin ? 'spin-icon' : ''} />
      {status}
      <style>{`.spin-icon { animation: spin 1s linear infinite; } @keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </span>
  )
}

function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}
