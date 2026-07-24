import { useState, useRef, useEffect, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Bot, User, X, Search, Code2, Terminal, Wrench, FileText,
  FolderOpen, ChevronDown, ChevronRight, ThumbsUp, ThumbsDown,
  RotateCcw, Paperclip, Send,
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
  const [filePreviewType, setFilePreviewType] = useState('text')
  const [wsTab, setWsTab] = useState('files')
  const [feedback, setFeedback] = useState({})
  const scrollRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    const handler = () => {
      setMessages([]); setShowWorkspace(false); setSelectedFile(null)
      setFileContent(''); setFeedback({})
    }
    window.addEventListener('arena-new-chat', handler)
    return () => window.removeEventListener('arena-new-chat', handler)
  }, [])

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, isStreaming, scrollToBottom])

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

  function handleFeedback(msgId, value) {
    setFeedback((prev) => ({ ...prev, [msgId]: value }))
    toast.success(value === 'yes' ? 'Thanks for the feedback!' : value === 'keep' ? 'Continuing…' : 'Feedback recorded')
  }

  async function openFile(path) {
    try {
      const data = await workspaceApi.readFile(path)
      setSelectedFile(path)
      setFileContent(data.content)
      setWsTab('preview')
      // Detect if it's HTML for iframe preview
      if (path.endsWith('.html') || path.endsWith('.htm')) {
        setFilePreviewType('html')
      } else {
        setFilePreviewType('text')
      }
    } catch { toast.error('Could not read file') }
  }

  const hasMessages = messages.length > 0
  const lastAgentMsg = [...messages].reverse().find(m => m.role === 'agent')

  return (
    <>
      <div className="chat-area">
        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-inner">
            {!hasMessages && !isStreaming ? (
              <WelcomeScreen onSuggestion={handleSuggestion} />
            ) : (
              <>
                {messages.map((msg) => (
                  <div key={msg.id}>
                    <div className="msg">
                      <div className={`msg-avatar ${msg.role}`}>
                        {msg.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                      </div>
                      <div className="msg-body">
                        <div className="msg-role">{msg.role === 'user' ? 'You' : 'Arena'}</div>
                        {msg.toolCalls?.length > 0 && (
                          <div className="tools-row">
                            {msg.toolCalls.map((tc, i) => (
                              <span key={i} className="tool-pill">
                                <ToolIcon name={tc.tool} />
                                {tc.tool}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="msg-text"><RenderContent content={msg.content} /></div>
                      </div>
                    </div>

                    {/* Feedback bar after last agent message */}
                    {msg.role === 'agent' && msg.id === lastAgentMsg?.id && !feedback[msg.id] && !isStreaming && (
                      <div className="feedback-bar">
                        <span className="feedback-label">Was this task successful?</span>
                        <button className="feedback-btn yes" onClick={() => handleFeedback(msg.id, 'yes')}>
                          <ThumbsUp size={13} /> Yes
                        </button>
                        <button className="feedback-btn no" onClick={() => handleFeedback(msg.id, 'no')}>
                          <ThumbsDown size={13} /> No
                        </button>
                        <button className="feedback-btn keep" onClick={() => handleFeedback(msg.id, 'keep')}>
                          <RotateCcw size={13} /> Keep working
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                {isStreaming && (
                  <div className="msg">
                    <div className="msg-avatar agent"><Bot size={14} /></div>
                    <div className="msg-body">
                      <div className="thinking">
                        <div className="thinking-dots">
                          <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
                        </div>
                        Thinking…
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Input bar */}
        <div className="input-area">
          <form className="input-wrapper" onSubmit={(e) => { e.preventDefault(); handleSubmit() }}>
            <div className="input-top">
              <textarea
                ref={inputRef}
                className="input-field"
                placeholder="What would you like to do?"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isStreaming}
                rows={1}
                onInput={(e) => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px' }}
              />
              <button type="button" className="input-action" style={{ padding: 6 }}>
                <Paperclip size={16} />
              </button>
              <button type="submit" className="input-send" disabled={!input.trim() || isStreaming}>
                <Send size={15} />
              </button>
            </div>
            <div className="input-bottom">
              <span className="input-disclaimer">
                Inputs are processed by AI and responses may be inaccurate.
              </span>
            </div>
          </form>
        </div>
      </div>

      {/* Workspace panel */}
      {showWorkspace && (
        <div className="workspace">
          <div className="ws-header">
            <span className="ws-title">Workspace</span>
            <button className="ws-close" onClick={() => setShowWorkspace(false)}><X size={16} /></button>
          </div>
          <div className="ws-tabs">
            {['files', 'preview'].map((t) => (
              <button key={t} className={`ws-tab${wsTab === t ? ' active' : ''}`} onClick={() => setWsTab(t)}>{t}</button>
            ))}
          </div>
          <div className="ws-body">
            {wsTab === 'files' && <FilesPanel onSelect={openFile} selected={selectedFile} />}
            {wsTab === 'preview' && (
              selectedFile ? (
                <div className="ws-preview">
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>{selectedFile}</div>
                  {filePreviewType === 'html' ? (
                    <iframe
                      className="ws-preview-iframe"
                      srcDoc={fileContent}
                      title="Preview"
                      sandbox="allow-scripts"
                    />
                  ) : (
                    <pre className="ws-preview-content">{fileContent}</pre>
                  )}
                </div>
              ) : (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                  Click a file to preview
                </div>
              )
            )}
          </div>
        </div>
      )}
    </>
  )
}

/* ── Files Panel ─────────────────────────────────────────────── */

function FilesPanel({ onSelect, selected }) {
  const { data: tree } = useQuery({
    queryKey: ['ws-tree'], queryFn: () => workspaceApi.tree(),
    staleTime: 5_000, refetchInterval: 8_000,
  })
  if (!tree?.length) return (
    <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
      Files created by the agent will appear here
    </div>
  )
  return <>{tree.map((n) => <TreeNode key={n.path} node={n} depth={0} onSelect={onSelect} selected={selected} />)}</>
}

function TreeNode({ node, depth, onSelect, selected }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const indent = depth * 14
  const ext = node.name.split('.').pop()?.toLowerCase()
  const colors = { py: '#3572A5', js: '#f1e05a', ts: '#3178c6', json: '#666', md: '#22c55e', html: '#e34c26', css: '#563d7c' }

  if (node.is_dir) return (
    <div>
      <div className="ws-file" style={{ paddingLeft: 8 + indent }} onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <FolderOpen size={13} style={{ color: 'var(--yellow)', opacity: 0.7 }} />
        <span className="ws-file-name">{node.name}</span>
      </div>
      {expanded && node.children?.map((c) => <TreeNode key={c.path} node={c} depth={depth + 1} onSelect={onSelect} selected={selected} />)}
    </div>
  )

  return (
    <div className={`ws-file${selected === node.path ? ' active' : ''}`} style={{ paddingLeft: 8 + indent }} onClick={() => onSelect(node.path)}>
      <span className="ws-file-icon" style={{ color: colors[ext] || '#666' }}>{ext?.toUpperCase().slice(0, 2) || '·'}</span>
      <span className="ws-file-name">{node.name}</span>
    </div>
  )
}

/* ── Tool Icon ───────────────────────────────────────────────── */

const TOOL_MAP = {
  read_file: FileText, write_file: FileText, list_files: FolderOpen,
  execute_code: Code2, run_code: Code2, shell: Terminal, bash: Terminal,
  command: Terminal, web_search: Search, search: Search,
  install: Wrench, system_info: Wrench,
}

function ToolIcon({ name }) {
  const Icon = TOOL_MAP[name] || Wrench
  return <span className="tool-pill-icon"><Icon size={11} /></span>
}

/* ── Welcome Screen — exact Arena.ai ─────────────────────────── */

function WelcomeScreen({ onSuggestion }) {
  const suggestions = [
    { title: 'Create a landing page', desc: 'Create a sleek, modern landing page' },
    { title: 'Build a dashboard', desc: 'Turn data into interactive charts' },
    { title: 'Make a game', desc: 'Build a playable browser game' },
    { title: 'Design to Code', desc: 'Upload an image and have AI build it' },
    { title: 'Build a fullstack app', desc: 'Create a templated full-stack app' },
    { title: 'Launch a storefront', desc: 'Create a beautiful online shop' },
  ]

  return (
    <div className="welcome">
      <h1>What would you like to do?</h1>
      <p className="welcome-sub">
        Arena can build apps, write code, research topics, and complete tasks autonomously.
      </p>
      <div className="welcome-grid">
        {suggestions.map((s) => (
          <div key={s.title} className="welcome-card" onClick={() => onSuggestion(s.title)}>
            <div className="welcome-card-title">{s.title}</div>
            {s.desc}
          </div>
        ))}
      </div>
      <div className="welcome-footer">
        <Paperclip size={12} style={{ verticalAlign: 'middle', marginRight: 4 }} />
        Drop files… Add files
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
        __html: line
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/`([^`]+)`/g, '<code>$1</code>')
          .replace(/!\[.*?\]\((.*?)\)/g, '<img src="$1" alt="Generated" />')
      }} />
    ))
  })
}
