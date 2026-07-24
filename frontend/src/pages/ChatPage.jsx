import { useState, useRef, useEffect, useCallback, memo } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Send, Bot, User, ChevronDown, Hammer, Brain, Plus, X,
  FileText, FolderOpen, Code2, Terminal, Search, Wrench,
} from 'lucide-react'
import { agentApi } from '../api/agent'
import { workspaceApi } from '../api/workspace'
import { apiErrorMessage } from '../api/client'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [showWorkspace, setShowWorkspace] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState('')
  const [wsTab, setWsTab] = useState('files')
  const messagesRef = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    const handler = () => { setMessages([]); setShowWorkspace(false); setSelectedFile(null) }
    window.addEventListener('arena-new-chat', handler)
    return () => window.removeEventListener('arena-new-chat', handler)
  }, [])

  const scrollToBottom = useCallback((smooth = true) => {
    messagesRef.current?.scrollTo({ top: messagesRef.current.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
  }, [])

  useEffect(() => { scrollToBottom(false) }, [messages.length])

  const chatMutation = useMutation({
    mutationFn: (msg) => agentApi.chat(msg),
    onMutate: (msg) => {
      setIsStreaming(true)
      setMessages((prev) => [...prev, { id: Date.now(), role: 'user', content: msg, timestamp: new Date() }])
      setInput('')
    },
    onSuccess: (data) => {
      setMessages((prev) => [...prev, {
        id: Date.now() + 1, role: 'agent', content: data.response,
        toolCalls: data.tool_calls || [], thinking: data.thinking, timestamp: new Date(),
      }])
      setIsStreaming(false)
      if (data.tool_calls?.length > 0) setShowWorkspace(true)
    },
    onError: (e) => { toast.error(apiErrorMessage(e)); setIsStreaming(false) },
  })

  function handleSubmit() {
    if (!input.trim() || isStreaming) return
    chatMutation.mutate(input.trim())
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  function handleSuggestion(text) {
    setInput(text)
    setTimeout(() => chatMutation.mutate(text), 50)
  }

  async function openFile(path) {
    try {
      const data = await workspaceApi.readFile(path)
      setSelectedFile(path)
      setFileContent(data.content)
      setWsTab('preview')
    } catch { toast.error('Could not read file') }
  }

  return (
    <div className="chat-layout">
      {/* Left sidebar — sessions */}
      <div className="chat-sidebar">
        <div className="chat-sidebar-header">
          <button className="btn btn-primary" style={{ width: '100%' }} onClick={() => window.dispatchEvent(new CustomEvent('arena-new-chat'))}>
            <Plus size={14} /> New Chat
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {messages.filter(m => m.role === 'user').map((m, i) => (
            <div key={i} className="file-item" style={{ padding: '10px 12px', marginBottom: 4 }}>
              <span style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {m.content.slice(0, 40)}{m.content.length > 40 ? '…' : ''}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Main chat area */}
      <div className="chat-main">
        <div className="chat-messages" ref={messagesRef}>
          <div className="chat-messages-inner">
            {messages.length === 0 && !isStreaming ? (
              <WelcomeScreen onSuggestion={handleSuggestion} />
            ) : (
              <>
                {messages.map((msg) => <Message key={msg.id} message={msg} />)}
                {isStreaming && <ThinkingLoader />}
              </>
            )}
          </div>
        </div>

        <div className="chat-input-area">
          <div className="chat-input-wrapper">
            <textarea
              ref={inputRef}
              className="chat-input"
              placeholder="What would you like to do?"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isStreaming}
              rows={1}
              onInput={(e) => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px' }}
            />
            <button ref={fileInputRef} type="button" className="btn btn-ghost" style={{ padding: '10px' }} onClick={() => document.getElementById('file-upload')?.click()}>
              📎
            </button>
            <input id="file-upload" type="file" style={{ display: 'none' }} />
            <button className="chat-send-btn" onClick={handleSubmit} disabled={!input.trim() || isStreaming}>
              <SendIcon />
            </button>
          </div>
          <div style={{ maxWidth: 800, margin: '8px auto 0', fontSize: 11, color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
            <span>Inputs are processed by AI and responses may be inaccurate.</span>
          </div>
        </div>
      </div>

      {/* Right workspace panel */}
      {showWorkspace && (
        <div className="workspace-panel">
          <div className="workspace-header">
            <span style={{ fontSize: 13, fontWeight: 600 }}>Workspace</span>
            <button onClick={() => setShowWorkspace(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
              <X size={16} />
            </button>
          </div>
          <div className="workspace-tabs">
            {['files', 'preview'].map((t) => (
              <button key={t} className={`workspace-tab${wsTab === t ? ' active' : ''}`} onClick={() => setWsTab(t)}>
                {t}
              </button>
            ))}
          </div>
          <div className="workspace-content">
            {wsTab === 'files' && <FilesPanel onSelect={openFile} selected={selectedFile} />}
            {wsTab === 'preview' && (
              selectedFile ? (
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{selectedFile}</div>
                  <pre style={{
                    margin: 0, padding: 12, background: '#1e1e1e', color: '#d4d4d4',
                    borderRadius: 8, fontSize: 12, fontFamily: 'var(--font-mono)',
                    whiteSpace: 'pre-wrap', overflow: 'auto', lineHeight: 1.5,
                  }}>{fileContent}</pre>
                </div>
              ) : <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>Click a file to preview</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Files Panel ─────────────────────────────────────────────── */

function FilesPanel({ onSelect, selected }) {
  const { data: tree } = useQuery({ queryKey: ['ws-tree'], queryFn: () => workspaceApi.tree(), staleTime: 10_000, refetchInterval: 10_000 })
  if (!tree?.length) return <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>Files will appear here</div>
  return <>{tree.map((n) => <TreeNode key={n.path} node={n} depth={0} onSelect={onSelect} selected={selected} />)}</>
}

function TreeNode({ node, depth, onSelect, selected }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const indent = depth * 12
  const ext = node.name.split('.').pop()?.toLowerCase()
  const colors = { py: '#3572A5', js: '#f1e05a', ts: '#3178c6', json: '#666', md: '#22c55e', html: '#e34c26' }

  if (node.is_dir) return (
    <div>
      <div className="file-item" style={{ paddingLeft: 8 + indent }} onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <FolderOpen size={13} style={{ color: '#eab308', opacity: 0.7 }} />
        <span>{node.name}</span>
      </div>
      {expanded && node.children?.map((c) => <TreeNode key={c.path} node={c} depth={depth + 1} onSelect={onSelect} selected={selected} />)}
    </div>
  )

  return (
    <div className="file-item" style={{ paddingLeft: 8 + indent, background: selected === node.path ? 'var(--bg-input)' : 'transparent' }} onClick={() => onSelect(node.path)}>
      <span className="file-icon" style={{ color: colors[ext] || '#666' }}>{ext?.toUpperCase().slice(0, 2) || '·'}</span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{node.name}</span>
    </div>
  )
}

/* ── Message ─────────────────────────────────────────────────── */

function Message({ message }) {
  const isUser = message.role === 'user'
  return (
    <div className="message">
      <div className={`message-avatar ${isUser ? 'user' : 'agent'}`}>
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className="message-body">
        <div className="message-role">{isUser ? 'You' : 'Arena'}</div>
        {message.toolCalls?.length > 0 && (
          <div className="tool-calls">
            {message.toolCalls.map((tc, i) => <div key={i} className="tool-pill">{tc.tool}</div>)}
          </div>
        )}
        <div className="message-content"><RenderContent content={message.content} /></div>
      </div>
    </div>
  )
}

function ThinkingLoader() {
  return (
    <div className="message">
      <div className="message-avatar agent"><Bot size={16} /></div>
      <div className="thinking-dots"><div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" /></div>
    </div>
  )
}

/* ── Welcome Screen ──────────────────────────────────────────── */

function WelcomeScreen({ onSuggestion }) {
  const suggestions = [
    'Create a landing page with HTML and CSS',
    'Build a Python script that scrapes a website',
    'Write a todo app in JavaScript',
    'Analyze the files in this project',
    'Create a REST API with FastAPI',
    'Build a React component for a login form',
  ]
  return (
    <div className="welcome">
      <div className="welcome-icon"><Bot size={32} color="white" /></div>
      <h1>What would you like to do?</h1>
      <p>Arena can build apps, write code, research topics, create files, and complete multi-step tasks — all from a single prompt.</p>
      <div className="welcome-suggestions">
        {suggestions.map((s) => (
          <div key={s} className="welcome-suggestion" onClick={() => onSuggestion(s)}>{s}</div>
        ))}
      </div>
    </div>
  )
}

/* ── Content Renderer ────────────────────────────────────────── */

function RenderContent({ content }) {
  if (!content) return null
  const parts = content.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const lines = part.slice(3, -3).split('\n')
      const lang = lines[0].trim()
      const code = lang ? lines.slice(1).join('\n') : lines.join('\n')
      return <pre key={i}><code>{code}</code></pre>
    }
    return part.split('\n').map((line, j) => (
      <p key={`${i}-${j}`} dangerouslySetInnerHTML={{
        __html: line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>')
      }} />
    ))
  })
}

/* ── Send Icon ───────────────────────────────────────────────── */

function SendIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M14 2L7 9M14 2L9.5 14L7 9M14 2L2 6.5L7 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
}
