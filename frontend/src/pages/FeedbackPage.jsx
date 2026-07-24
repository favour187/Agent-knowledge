import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, ThumbsUp } from 'lucide-react'
import { feedbackApi } from '../api/feedback'
import { apiErrorMessage } from '../api/client'
import { SkeletonTable, EmptyState, ErrorBanner, Modal } from '../components/ui/Primitives'

export default function FeedbackPage() {
  const [createOpen, setCreateOpen] = useState(false)
  const { data: feedback, isLoading, error } = useQuery({ queryKey: ['feedback'], queryFn: feedbackApi.list })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Feedback</h1>
          <p className="page-subtitle">Human feedback used to steer agent behavior over time.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> Add feedback
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && (
        <div className="card" style={{ padding: 0 }}>
          <SkeletonTable rows={4} cols={5} />
        </div>
      )}

      {feedback && feedback.length === 0 && (
        <EmptyState title="No feedback recorded yet" hint="Feedback on agent outputs will appear here." icon={ThumbsUp} />
      )}

      {feedback && feedback.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Output</th>
                <th>Result</th>
                <th>Rating</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {feedback.map((fb) => (
                <tr key={fb.id}>
                  <td className="mono">{fb.feedback_type}</td>
                  <td style={{ maxWidth: 320 }} className="text-muted">{fb.output}</td>
                  <td>
                    <span className={`badge ${fb.success ? 'status-success' : 'status-failed'}`}>
                      <span className="badge-dot" />
                      {fb.success ? 'success' : 'issue'}
                    </span>
                  </td>
                  <td className="mono text-muted">{fb.rating ?? '—'}</td>
                  <td className="text-muted">{new Date(fb.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && <CreateFeedbackModal onClose={() => setCreateOpen(false)} />}
    </div>
  )
}

function CreateFeedbackModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ feedback_type: 'general', context: '', output: '', expected: '', success: true, rating: 3 })

  const mutation = useMutation({
    mutationFn: () => feedbackApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['feedback'] })
      toast.success('Feedback recorded')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="Add feedback" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Type</label>
          <input className="input" value={form.feedback_type} onChange={(e) => setForm({ ...form, feedback_type: e.target.value })} />
        </div>
        <div className="field">
          <label>Output</label>
          <textarea className="textarea" rows={3} required value={form.output} onChange={(e) => setForm({ ...form, output: e.target.value })} />
        </div>
        <div className="field">
          <label>Expected (optional)</label>
          <textarea className="textarea" rows={2} value={form.expected} onChange={(e) => setForm({ ...form, expected: e.target.value })} />
        </div>
        <div className="field">
          <label>Rating (1–5)</label>
          <input
            className="input"
            type="number"
            min={1}
            max={5}
            value={form.rating}
            onChange={(e) => setForm({ ...form, rating: Number(e.target.value) })}
          />
        </div>
        <div className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <input
            id="success"
            type="checkbox"
            checked={form.success}
            onChange={(e) => setForm({ ...form, success: e.target.checked })}
            style={{ accentColor: 'var(--amber)' }}
          />
          <label htmlFor="success" style={{ margin: 0, cursor: 'pointer' }}>Marked as successful</label>
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save feedback'}
        </button>
      </form>
    </Modal>
  )
}
