import { useState, useRef, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Send, Bot, User, Square, Paperclip, Terminal } from 'lucide-react'
import { sessionsApi } from '../api/sessions'
import { agentsApi } from '../api/agents'
import { apiErrorMessage } from '../api/client'
import { Spinner, Modal } from '../components/ui/Primitives'
import { formatDistanceToNow } from 'date-fns'

export default function SessionsPage() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)

  const { data: sessions, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: sessionsApi.list,
  })

  const selected = sessions?.find((s) => s.id === selectedId) || null

  if (!selected) {
    return <ChatWelcome onNew={() => setCreateOpen(true)} sessions={sessions} onSelect={setSelectedId} />
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <ChatView session={selected} onBack={() => setSelectedId(null)} />
      {createOpen && (
        <CreateSessionModal
          onClose={() => setCreateOpen(false)}
          onCreated={(id) => { setSelectedId(id); setCreateOpen(false) }}
        />
      )}
    </div>
  )
}

function ChatWelcome({ onNew, sessions, onSelect }) {
  return (
    <div style={{ flex: 1, overflow: 'auto' }}>
      <div className="chat-welcome">
        <div className="chat-welcome-icon">
          <Bot size={32} color="white" />
        </div>
        <h2>Arena Chat</h2>
        <p>
          Start a conversation with an AI agent. Ask questions, write code,
          analyze data, or automate tasks.
        </p>

        <div style={{ marginBottom: 24 }}>
          <button className="btn btn-primary" onClick={onNew}>
            <Plus size={16} /> New conversation
          </button>
        </div>

        {sessions && sessions.length > 0 && (
          <div style={{ width: '100%', maxWidth: 500 }}>
            <h3 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12, textAlign: 'left' }}>
              Recent conversations
            </h3>
            {sessions.slice(0, 5).map((s) => (
              <div
                key={s.id}
                className="card"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  marginBottom: 8,
                  cursor: 'pointer',
                }}
                onClick={() => onSelect(s.id)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 'var(--radius-md)',
                    background: 'var(--accent-green-dim)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Bot size={16} style={{ color: 'var(--accent-green)' }} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{s.title || 'Untitled'}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      {s.message_count} messages
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ChatView({ session, onBack }) {
  const qc = useQueryClient()
  const [content, setContent] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  const { data: messages, isLoading } = useQuery({
    queryKey: ['sessions', session.id, 'messages'],
    queryFn: () => sessionsApi.messages(session.id),
  })

  const sendMutation = useMutation({
    mutationFn: (payload) => sessionsApi.sendMessage(session.id, payload),
    onMutate: () => setIsTyping(true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sessions', session.id, 'messages'] })
      qc.invalidateQueries({ queryKey: ['sessions'] })
      setContent('')
      setIsTyping(false)
    },
    onError: (e) => {
      toast.error(apiErrorMessage(e))
      setIsTyping(false)
    },
  })

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isTyping])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (content.trim()) sendMutation.mutate({ content, role: 'user' })
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (content.trim()) sendMutation.mutate({ content, role: 'user' })
  }

  return (
    <>
      <div className="chat-messages">
        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
            <Spinner />
          </div>
        )}

        {messages?.map((msg) => (
          <div key={msg.id} className="chat-message">
            <div className={`chat-message-avatar ${msg.role}`}>
              {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
            </div>
            <div className="chat-message-content">
              <div className="chat-message-role">
                {msg.role === 'user' ? 'You' : 'Arena'}
                <span className="time">
                  {formatDistanceToNow(new Date(msg.created_at), { addSuffix: true })}
                </span>
              </div>
              <div className="chat-message-text">
                <MessageContent content={msg.content} />
              </div>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="chat-message">
            <div className="chat-message-avatar assistant">
              <Bot size={14} />
            </div>
            <div className="chat-message-content">
              <div className="chat-message-role">Arena</div>
              <div style={{ display: 'flex', gap: 4, padding: '8px 0' }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-muted)', animation: 'pulse 1.4s ease-in-out infinite' }} />
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-muted)', animation: 'pulse 1.4s ease-in-out 0.2s infinite' }} />
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--text-muted)', animation: 'pulse 1.4s ease-in-out 0.4s infinite' }} />
              </div>
              <style>{`@keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }`}</style>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <form className="chat-input-wrapper" onSubmit={handleSubmit}>
          <div className="chat-input-top">
            <textarea
              ref={textareaRef}
              className="chat-input"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Arena…"
              rows={1}
              style={{ height: 'auto' }}
              onInput={(e) => {
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
              }}
            />
            <button
              type="submit"
              className="chat-input-send"
              disabled={!content.trim() || sendMutation.isPending}
            >
              <Send size={16} />
            </button>
          </div>
          <div className="chat-input-bottom">
            <button type="button" className="chat-input-action">
              <Paperclip size={13} /> Attach
            </button>
            <button type="button" className="chat-input-action">
              <Terminal size={13} /> Tools
            </button>
            <div className="chat-input-model">
              <Bot size={12} /> Arena Agent
            </div>
          </div>
        </form>
      </div>
    </>
  )
}

function MessageContent({ content }) {
  if (!content) return null

  // Simple markdown-like rendering
  const parts = content.split(/(```[\s\S]*?```|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g)

  return (
    <>
      {parts.map((part, i) => {
        // Code blocks
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).split('\n')
          const lang = lines[0].trim()
          const code = lang ? lines.slice(1).join('\n') : lines.join('\n')
          return (
            <div key={i}>
              {lang && <div className="code-header"><span>{lang}</span></div>}
              <pre><code>{code}</code></pre>
            </div>
          )
        }
        // Inline code
        if (part.startsWith('`') && part.endsWith('`')) {
          return <code key={i}>{part.slice(1, -1)}</code>
        }
        // Bold
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i}>{part.slice(2, -2)}</strong>
        }
        // Italic
        if (part.startsWith('*') && part.endsWith('*')) {
          return <em key={i}>{part.slice(1, -1)}</em>
        }
        // Regular text with line breaks
        return (
          <span key={i}>
            {part.split('\n').map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {line}
              </span>
            ))}
          </span>
        )
      })}
    </>
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
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New conversation" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }}>
        <div className="field">
          <label>Agent</label>
          <select className="select" required value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            <option value="" disabled>Choose an agent</option>
            {agents?.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Title (optional)</label>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Give it a name" />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending || !agentId}>
          {mutation.isPending ? 'Creating…' : 'Start conversation'}
        </button>
      </form>
    </Modal>
  )
}
