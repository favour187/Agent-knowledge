import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, ListChecks } from 'lucide-react'
import { tasksApi } from '../api/tasks'
import { apiErrorMessage } from '../api/client'
import { StatusBadge, SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

const STATUSES = ['pending', 'running', 'completed', 'failed']

export default function TasksPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const { data: tasks, isLoading, error } = useQuery({ queryKey: ['tasks'], queryFn: tasksApi.list })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }) => tasksApi.update(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }),
    onError: (e) => toast.error(apiErrorMessage(e)),
  })
  const removeMutation = useMutation({
    mutationFn: tasksApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Tasks</h1>
          <p className="page-subtitle">Units of work assigned to agents, tracked to completion.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New task
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && (
        <div className="card" style={{ padding: 0 }}>
          <SkeletonTable rows={4} cols={5} />
        </div>
      )}

      {tasks && tasks.length === 0 && (
        <EmptyState
          title="No tasks yet"
          hint="Create a task to queue work for an agent."
          icon={ListChecks}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> New task
            </button>
          }
        />
      )}

      {tasks && tasks.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{task.title}</div>
                    {task.description && <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>{task.description}</div>}
                  </td>
                  <td className="mono text-muted">{task.priority}</td>
                  <td>
                    <select
                      className="select"
                      style={{ width: 'auto', padding: '4px 8px', fontSize: 12 }}
                      value={task.status}
                      onChange={(e) => updateMutation.mutate({ id: task.id, payload: { status: e.target.value } })}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td className="text-muted">{new Date(task.created_at).toLocaleDateString()}</td>
                  <td>
                    <ConfirmButton onConfirm={() => removeMutation.mutate(task.id)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && <CreateTaskModal onClose={() => setCreateOpen(false)} />}
    </div>
  )
}

function CreateTaskModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ title: '', description: '', priority: 0 })

  const mutation = useMutation({
    mutationFn: () => tasksApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task created')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New task" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Title</label>
          <input className="input" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </div>
        <div className="field">
          <label>Description</label>
          <textarea className="textarea" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <div className="field">
          <label>Priority (0–100)</label>
          <input
            className="input"
            type="number"
            min={0}
            max={100}
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
          />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create task'}
        </button>
      </form>
    </Modal>
  )
}
