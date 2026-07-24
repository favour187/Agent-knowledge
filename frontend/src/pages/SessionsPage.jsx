import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Send, MessagesSquare } from 'lucide-react'
import { sessionsApi } from '../api/sessions'
import { agentsApi } from '../api/agents'
import { apiErrorMessage } from '../api/client'
import { SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton, Spinner } from '../components/ui/Primitives'
import { formatDistanceToNow } from 'date-fns'

export default function SessionsPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedId, setSelectedId] = useState(null)

  const { data: sessions, isLoading, error } = useQuery({ queryKey: ['sessions'], queryFn: sessionsApi.list })

  const removeMutation = useMutation({
    mutationFn: sessionsApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      if (selectedId) setSelectedId(null)
      toast.success('Session deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  const selected = sessions?.find((s) => s.id === selectedId) || null

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Sessions</h1>
          <p className="page-subtitle">Conversation threads between you and your agents.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New session
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonTable rows={5} cols={3} />}

      {sessions && sessions.length === 0 && (
        <EmptyState
          title="No sessions yet"
          hint="Start a session with an agent to begin a conversation."
          icon={MessagesSquare}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> New session
            </button>
          }
        />
      )}

      {sessions && sessions.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, alignItems: 'start' }}>
          <div className="card" style={{ padding: 6 }}>
            {sessions.map((s) => (
              <div
                key={s.id}
                onClick={() => setSelectedId(s.id)}
                className={`nav-link${selectedId === s.id ? ' active' : ''}`}
                style={{ cursor: 'pointer', marginBottom: 2 }}
              >
                <span className="nav-link-left" style={{ minWidth: 0 }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                    {s.title || 'Untitled session'}
                  </span>
                </span>
                <span className="nav-link-count">{s.message_count}</span>
              </div>
            ))}
          </div>

          {selected ? (
            <SessionChat session={selected} onDelete={() => removeMutation.mutate(selected.id)} />
          ) : (
            <div className="card">
              <EmptyState title="Select a session" hint="Pick a session from the list to view its messages." icon={MessagesSquare} />
            </div>
          )}
        </div>
      )}

      {createOpen && (
        <CreateSessionModal
          onClose={() => setCreateOpen(false)}
          onCreated={(id) => setSelectedId(id)}
        />
      )}
    </div>
  )
}

function SessionChat({ session, onDelete }) {
  const qc = useQueryClient()
  const [content, setContent] = useState('')

  const { data: messages, isLoading } = useQuery({
    queryKey: ['sessions', session.id, 'messages'],
    queryFn: () => sessionsApi.messages(session.id),
  })

  const sendMutation = useMutation({
    mutationFn: (payload) => sessionsApi.sendMessage(session.id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sessions', session.id, 'messages'] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setContent('')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', minHeight: 420 }}>
      <div className="flex-between" style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 14 }}>{session.title || 'Untitled session'}</h3>
        <ConfirmButton onConfirm={onDelete} />
      </div>

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
            <Spinner />
          </div>
        )}
        {messages && messages.length === 0 && (
          <p className="text-muted" style={{ fontSize: 13, textAlign: 'center', padding: 20 }}>No messages yet.</p>
        )}
        {messages?.map((m) => (
          <div key={m.id} className={`chat-bubble ${m.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-agent'}`}>
            <div className="chat-bubble-role">
              {m.role} · {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}
            </div>
            {m.content}
          </div>
        ))}
      </div>

      <form
        className="flex-row"
        onSubmit={(e) => {
          e.preventDefault()
          if (content.trim()) sendMutation.mutate({ content, role: 'user' })
        }}
      >
        <input className="input" value={content} onChange={(e) => setContent(e.target.value)} placeholder="Send a message…" />
        <button className="btn btn-primary btn-sm" disabled={sendMutation.isPending}>
          <Send size={13} />
        </button>
      </form>
    </div>
  )
}

function CreateSessionModal({ onClose, onCreated }) {
  const qc = useQueryClient()
  const [agentId, setAgentId] = useState('')
  const [title, setTitle] = useState('')

  const { data: agents } = useQuery({ queryKey: ['agents'], queryFn: agentsApi.list })

  const mutation = useMutation({
    mutationFn: () => sessionsApi.create({ agent_id: agentId, title: title || undefined }),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ['sessions'] })
      toast.success('Session created')
      onCreated(session.id)
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New session" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Agent</label>
          <select className="select" required value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            <option value="" disabled>
              Choose an agent
            </option>
            {agents?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          {agents && agents.length === 0 && (
            <span className="field-hint">You'll need to create an agent first.</span>
          )}
        </div>
        <div className="field">
          <label>Title (optional)</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Session title" />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending || !agentId}>
          {mutation.isPending ? 'Creating…' : 'Create session'}
        </button>
      </form>
    </Modal>
  )
}
