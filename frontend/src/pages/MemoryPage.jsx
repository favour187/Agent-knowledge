import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Search, Layers, BrainCircuit } from 'lucide-react'
import { memoryApi } from '../api/memory'
import { apiErrorMessage } from '../api/client'
import { SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

export default function MemoryPage() {
  const qc = useQueryClient()
  const [query, setQuery] = useState('')
  const [activeQuery, setActiveQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['memory', activeQuery],
    queryFn: () => memoryApi.search(activeQuery || ''),
  })

  const removeMutation = useMutation({
    mutationFn: memoryApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['memory'] })
      toast.success('Memory deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  const consolidateMutation = useMutation({
    mutationFn: memoryApi.consolidate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['memory'] })
      toast.success('Consolidation triggered')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Memory</h1>
          <p className="page-subtitle">Episodic, semantic, and procedural memory across your agents.</p>
        </div>
        <div className="flex-row">
          <button className="btn" onClick={() => consolidateMutation.mutate()} disabled={consolidateMutation.isPending}>
            <Layers size={15} /> Consolidate
          </button>
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> Add memory
          </button>
        </div>
      </div>

      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault()
          setActiveQuery(query)
        }}
      >
        <div style={{ position: 'relative', flex: 1, maxWidth: 420 }}>
          <input
            className="input"
            style={{ paddingLeft: 34 }}
            placeholder="Search memory…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Search size={14} style={{ position: 'absolute', left: 11, top: 11, color: 'var(--text-muted)' }} />
        </div>
        <button className="btn btn-sm">Search</button>
      </form>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && (
        <div className="card" style={{ padding: 0 }}>
          <SkeletonTable rows={5} cols={5} />
        </div>
      )}

      {data && data.results.length === 0 && (
        <EmptyState title="No memories found" hint="Try a different search, or add a new memory." icon={BrainCircuit} />
      )}

      {data && data.results.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Content</th>
                <th>Type</th>
                <th>Importance</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((m) => (
                <tr key={m.id}>
                  <td style={{ maxWidth: 420 }}>{m.content}</td>
                  <td className="mono text-muted">{m.memory_type}</td>
                  <td className="mono text-muted">{m.importance.toFixed(2)}</td>
                  <td className="text-muted">{new Date(m.created_at).toLocaleDateString()}</td>
                  <td>
                    <ConfirmButton onConfirm={() => removeMutation.mutate(m.id)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && <CreateMemoryModal onClose={() => setCreateOpen(false)} />}
    </div>
  )
}

function CreateMemoryModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ content: '', memory_type: 'episodic', importance: 0.5 })

  const mutation = useMutation({
    mutationFn: () => memoryApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['memory'] })
      toast.success('Memory added')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="Add memory" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Content</label>
          <textarea className="textarea" rows={3} required value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />
        </div>
        <div className="field">
          <label>Type</label>
          <select className="select" value={form.memory_type} onChange={(e) => setForm({ ...form, memory_type: e.target.value })}>
            <option value="episodic">episodic</option>
            <option value="semantic">semantic</option>
            <option value="procedural">procedural</option>
          </select>
        </div>
        <div className="field">
          <label>Importance (0–1)</label>
          <input
            className="input"
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={form.importance}
            onChange={(e) => setForm({ ...form, importance: Number(e.target.value) })}
          />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Adding…' : 'Add memory'}
        </button>
      </form>
    </Modal>
  )
}
