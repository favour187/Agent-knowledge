import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Play, Square, MessageCircle, Bot } from 'lucide-react'
import { agentsApi } from '../api/agents'
import { apiErrorMessage } from '../api/client'
import { StatusBadge, SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

export default function AgentsPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [messageAgent, setMessageAgent] = useState(null)

  const { data: agents, isLoading, error } = useQuery({ queryKey: ['agents'], queryFn: agentsApi.list })

  const startMutation = useMutation({
    mutationFn: agentsApi.start,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
    onError: (e) => toast.error(apiErrorMessage(e)),
  })
  const stopMutation = useMutation({
    mutationFn: agentsApi.stop,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
    onError: (e) => toast.error(apiErrorMessage(e)),
  })
  const removeMutation = useMutation({
    mutationFn: agentsApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      toast.success('Agent deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Agents</h1>
          <p className="page-subtitle">Configure and run the agents that act on your behalf.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New agent
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />

      {isLoading && (
        <div className="card" style={{ padding: 0 }}>
          <SkeletonTable rows={4} cols={5} />
        </div>
      )}

      {agents && agents.length === 0 && (
        <EmptyState
          title="No agents yet"
          hint="Create an agent to give it a model, a system prompt, and tools."
          icon={Bot}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> New agent
            </button>
          }
        />
      )}

      {agents && agents.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Model</th>
                <th>Status</th>
                <th>Created</th>
                <th style={{ width: 120 }}></th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id}>
                  <td>
                    <div style={{ fontWeight: 500 }}>{agent.name}</div>
                    {agent.description && (
                      <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
                        {agent.description}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {agent.model}
                    </span>
                  </td>
                  <td>
                    <StatusBadge status={agent.status} />
                  </td>
                  <td className="text-muted">{new Date(agent.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="flex-row gap-sm">
                      <button
                        className="btn-icon"
                        onClick={() => setMessageAgent(agent)}
                        title="Message"
                      >
                        <MessageCircle size={14} />
                      </button>
                      {agent.status === 'running' ? (
                        <button
                          className="btn-icon"
                          onClick={() => stopMutation.mutate(agent.id)}
                          title="Stop"
                          style={{ color: 'var(--danger)' }}
                        >
                          <Square size={14} />
                        </button>
                      ) : (
                        <button
                          className="btn-icon"
                          onClick={() => startMutation.mutate(agent.id)}
                          title="Start"
                          style={{ color: 'var(--teal)' }}
                        >
                          <Play size={14} />
                        </button>
                      )}
                      <ConfirmButton onConfirm={() => removeMutation.mutate(agent.id)} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && <CreateAgentModal onClose={() => setCreateOpen(false)} />}
      {messageAgent && <MessageAgentModal agent={messageAgent} onClose={() => setMessageAgent(null)} />}
    </div>
  )
}

function CreateAgentModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name: '',
    description: '',
    model: 'gpt-4-turbo-preview',
    system_prompt: '',
    temperature: 0.7,
  })

  const mutation = useMutation({
    mutationFn: () => agentsApi.create(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      toast.success('Agent created')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New agent" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Name</label>
          <input
            className="input"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Research assistant"
          />
        </div>
        <div className="field">
          <label>Description</label>
          <input
            className="input"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="What this agent is for"
          />
        </div>
        <div className="field">
          <label>Model</label>
          <input className="input mono" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
        </div>
        <div className="field">
          <label>System prompt</label>
          <textarea
            className="textarea"
            rows={4}
            value={form.system_prompt}
            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
            placeholder="Leave blank to use the default assistant prompt"
          />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create agent'}
        </button>
      </form>
    </Modal>
  )
}

function MessageAgentModal({ agent, onClose }) {
  const [content, setContent] = useState('')
  const [thread, setThread] = useState([])

  const mutation = useMutation({
    mutationFn: () => agentsApi.message(agent.id, content),
    onSuccess: (res) => {
      setThread((t) => [...t, { role: 'user', content }, { role: 'agent', content: res.content }])
      setContent('')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title={`Message ${agent.name}`} onClose={onClose} width={560}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 320, overflowY: 'auto', marginBottom: 14 }}>
        {thread.length === 0 && (
          <p className="text-muted" style={{ fontSize: 13 }}>Send a message to this agent directly.</p>
        )}
        {thread.map((m, i) => (
          <div key={i} className={`chat-bubble ${m.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-agent'}`}>
            <div className="chat-bubble-role">{m.role}</div>
            {m.content}
          </div>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (content.trim()) mutation.mutate()
        }}
        className="flex-row"
      >
        <input
          className="input"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Type a message…"
        />
        <button className="btn btn-primary btn-sm" disabled={mutation.isPending}>
          Send
        </button>
      </form>
    </Modal>
  )
}
