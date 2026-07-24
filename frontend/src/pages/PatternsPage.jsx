import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Sparkles } from 'lucide-react'
import { patternsApi } from '../api/patterns'
import { apiErrorMessage } from '../api/client'
import { SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

export default function PatternsPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const { data: patterns, isLoading, error } = useQuery({ queryKey: ['patterns'], queryFn: patternsApi.list })

  const removeMutation = useMutation({
    mutationFn: patternsApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patterns'] })
      toast.success('Pattern deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Learned patterns</h1>
          <p className="page-subtitle">Reusable response patterns your agents pick up from experience.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New pattern
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && (
        <div className="card" style={{ padding: 0 }}>
          <SkeletonTable rows={4} cols={4} />
        </div>
      )}

      {patterns && patterns.length === 0 && (
        <EmptyState
          title="No patterns learned yet"
          hint="Patterns accumulate as agents succeed at tasks, or add one manually."
          icon={Sparkles}
        />
      )}

      {patterns && patterns.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Key</th>
                <th>Success rate</th>
                <th>Uses</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {patterns.map((p) => (
                <tr key={p.id}>
                  <td>
                    <div className="mono" style={{ fontWeight: 500 }}>{p.pattern_key}</div>
                    {p.context && <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>{p.context}</div>}
                  </td>
                  <td className="mono text-muted">{Math.round(p.success_rate * 100)}%</td>
                  <td className="mono text-muted">{p.usage_count}</td>
                  <td>
                    <ConfirmButton onConfirm={() => removeMutation.mutate(p.id)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && <CreatePatternModal onClose={() => setCreateOpen(false)} />}
    </div>
  )
}

function CreatePatternModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ pattern_key: '', context: '', response: '' })

  const mutation = useMutation({
    mutationFn: () => patternsApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patterns'] })
      toast.success('Pattern created')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New pattern" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Pattern key</label>
          <input className="input mono" required value={form.pattern_key} onChange={(e) => setForm({ ...form, pattern_key: e.target.value })} />
        </div>
        <div className="field">
          <label>Context</label>
          <textarea className="textarea" rows={2} value={form.context} onChange={(e) => setForm({ ...form, context: e.target.value })} />
        </div>
        <div className="field">
          <label>Response</label>
          <textarea className="textarea" rows={2} value={form.response} onChange={(e) => setForm({ ...form, response: e.target.value })} />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create pattern'}
        </button>
      </form>
    </Modal>
  )
}
