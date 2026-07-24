import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Gauge } from 'lucide-react'
import { evaluationApi } from '../api/evaluation'
import { apiErrorMessage } from '../api/client'
import { SkeletonTable, EmptyState, ErrorBanner, Modal } from '../components/ui/Primitives'

export default function EvaluationPage() {
  const [runOpen, setRunOpen] = useState(false)
  const { data: evals, isLoading, error } = useQuery({ queryKey: ['evaluation'], queryFn: evaluationApi.list })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Evaluation</h1>
          <p className="page-subtitle">Self-evaluation scores for agent output against a rubric.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setRunOpen(true)}>
          <Plus size={15} /> Run evaluation
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonTable rows={4} cols={3} />}

      {evals && evals.length === 0 && (
        <EmptyState
          title="No evaluations yet"
          hint="Run an evaluation against a piece of output to score it against a rubric."
          icon={Gauge}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setRunOpen(true)}>
              <Plus size={14} /> Run evaluation
            </button>
          }
        />
      )}

      {evals && evals.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {evals.map((ev) => (
            <div key={ev.id} className="card">
              <div className="flex-row" style={{ justifyContent: 'space-between' }}>
                <span className={`badge ${ev.passed ? 'status-passed' : 'status-failed'}`}>
                  <span className="badge-dot" />
                  {ev.passed ? 'passed' : 'failed'}
                </span>
                <span className="mono text-muted" style={{ fontSize: 12 }}>
                  {ev.overall_score != null ? `${Math.round(ev.overall_score * 100)}%` : '—'} · {ev.rubric_name || 'default'}
                </span>
              </div>
              <p style={{ fontSize: 13.5, marginTop: 10 }}>{ev.output}</p>
              {ev.suggestions?.length > 0 && (
                <ul style={{ marginTop: 10, paddingLeft: 18, fontSize: 12.5 }} className="text-muted">
                  {ev.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {runOpen && <RunEvaluationModal onClose={() => setRunOpen(false)} />}
    </div>
  )
}

function RunEvaluationModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ output: '', task: '', rubric_name: '' })

  const mutation = useMutation({
    mutationFn: () =>
      evaluationApi.run({
        output: form.output,
        task: form.task || undefined,
        rubric_name: form.rubric_name || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['evaluation'] })
      toast.success('Evaluation complete')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="Run evaluation" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Task (optional)</label>
          <input className="input" value={form.task} onChange={(e) => setForm({ ...form, task: e.target.value })} placeholder="What was the agent asked to do?" />
        </div>
        <div className="field">
          <label>Output to evaluate</label>
          <textarea
            className="textarea"
            rows={5}
            required
            value={form.output}
            onChange={(e) => setForm({ ...form, output: e.target.value })}
            placeholder="Paste the agent's output here"
          />
        </div>
        <div className="field">
          <label>Rubric (optional)</label>
          <input className="input mono" value={form.rubric_name} onChange={(e) => setForm({ ...form, rubric_name: e.target.value })} placeholder="coding" />
          <span className="field-hint">Leave blank to use the default rubric.</span>
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Evaluating…' : 'Run evaluation'}
        </button>
      </form>
    </Modal>
  )
}
