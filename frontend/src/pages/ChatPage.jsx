import { useState, useRef, useEffect, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Bot, User, X, Search, Code2, Terminal, Wrench, FileText,
  FolderOpen, ChevronDown, ChevronRight, ThumbsUp, ThumbsDown,
  RotateCcw, Paperclip, Send, PanelRightOpen, Github,
  Download, ChevronUp, Image,
} from 'lucide-react'
import { agentApi } from '../api/agent'
import { workspaceApi } from '../api/workspace'
import { apiErrorMessage } from '../api/client'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [streamingActions, setStreamingActions] = useState([])
  const [showWorkspace, setShowWorkspace] = useState(true)
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState('')
  const [filePreviewType, setFilePreviewType] = useState('text')
  const [wsTab, setWsTab] = useState('files')
  const [feedback, setFeedback] = useState({})
  const [sessionId, setSessionId] = useState(null)
  const [attachedFiles, setAttachedFiles] = useState([])
  const scrollRef = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const dropRef = useRef(null)

  // Events
  useEffect(() => {
    const newChat = () => {
      setMessages([]); setSelectedFile(null); setFileContent('')
      setFeedback({}); setSessionId(null); setAttachedFiles([])
    }
    const toggleWs = () => setShowWorkspace(v => !v)
    window.addEventListener('arena-new-chat', newChat)
    window.addEventListener('arena-toggle-ws', toggleWs)
    return () => {
      window.removeEventListener('arena-new-chat', newChat)
      window.removeEventListener('arena-toggle-ws', toggleWs)
    }
  }, [])

  // Drag and drop
  useEffect(() => {
    const el = dropRef.current
    if (!el) return
    const handleDragOver = (e) => { e.preventDefault(); el.style.borderColor = 'var(--accent)' }
    const handleDragLeave = () => { el.style.borderColor = 'var(--border)' }
    const handleDrop = (e) => {
      e.preventDefault()
      el.style.borderColor = 'var(--border)'
      const files = Array.from(e.dataTransfer.files)
      files.forEach(f => handleFileUpload(f))
    }
    el.addEventListener('dragover', handleDragOver)
    el.addEventListener('dragleave', handleDragLeave)
    el.addEventListener('drop', handleDrop)
    return () => {
      el.removeEventListener('dragover', handleDragOver)
      el.removeEventListener('dragleave', handleDragLeave)
      el.removeEventListener('drop', handleDrop)
    }
  }, [])

  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, isStreaming, streamingContent, scrollToBottom])

  // File upload handler
  async function handleFileUpload(file) {
    try {
      const result = await agentApi.upload(file)
      setAttachedFiles(prev => [...prev, result])
      toast.success(`Uploaded ${file.name}`)
      setShowWorkspace(true)
    } catch (e) {
      toast.error('Upload failed')
    }
  }

  function handleFileInputChange(e) {
    const files = Array.from(e.target.files || [])
    files.forEach(f => handleFileUpload(f))
    e.target.value = ''
  }

  // Chat submission — uses streaming
  async function handleSubmit() {
    if (!input.trim() || isStreaming) return
    const msg = input.trim()
    setInput('')
    setIsStreaming(true)
    setStreamingContent('')
    setStreamingActions([])

    // Add user message
    setMessages(prev => [...prev, {
      id: Date.now(), role: 'user', content: msg,
      attachments: attachedFiles.length > 0 ? [...attachedFiles] : null,
      timestamp: new Date(),
    }])
    setAttachedFiles([])

    // Add file context to message if files are attached
    let fullMessage = msg
    if (attachedFiles.length > 0) {
      const fileContext = attachedFiles.map(f => `[File: ${f.filename}]\n${f.content_preview || ''}`).join('\n\n')
      fullMessage = `${msg}\n\n--- Attached files ---\n${fileContext}`
    }

    try {
      let finalResponse = ''
      let toolCalls = []
      let actions = []
      let thinking = null

      // Try streaming first
      try {
        for await (const data of agentApi.chatStream(fullMessage, sessionId)) {
          if (data.type === 'thinking') {
            // Thinking phase
          } else if (data.type === 'token') {
            setStreamingContent(prev => prev + data.content)
            finalResponse += data.content
          } else if (data.type === 'tool_start') {
            const action = { tool: data.tool, arguments: data.arguments, status: 'running' }
            setStreamingActions(prev => [...prev, action])
            actions.push(action)
          } else if (data.type === 'tool_result') {
            setStreamingActions(prev => prev.map(a =>
              a.tool === data.tool ? { ...a, status: data.success ? 'success' : 'error', result: data.result } : a
            ))
            toolCalls.push({ tool: data.tool, result: data.result, success: data.success })
          } else if (data.type === 'done') {
            // Stream complete
          }
        }
      } catch {
        // Fallback to non-streaming
        const data = await agentApi.chat(fullMessage, sessionId)
        finalResponse = data.response
        toolCalls = data.tool_calls || []
        actions = data.actions || []
        thinking = data.thinking
        setStreamingContent(finalResponse)
      }

      // Add assistant message
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'agent', content: finalResponse,
        toolCalls, actions, thinking, timestamp: new Date(),
      }])
      setStreamingContent('')
      setStreamingActions([])

    } catch (e) {
      toast.error(apiErrorMessage(e))
    } finally {
      setIsStreaming(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  function handleSuggestion(text) {
    setInput(text)
    setTimeout(() => handleSubmit(), 50)
  }

  function handleFeedback(msgId, value) {
    setFeedback(prev => ({ ...prev, [msgId]: value }))
    toast.success(value === 'yes' ? 'Thanks!' : value === 'keep' ? 'Continuing…' : 'Recorded')
  }

  async function openFile(path) {
    try {
      const data = await workspaceApi.readFile(path)
      setSelectedFile(path)
      setFileContent(data.content)
      setWsTab('preview')
      setFilePreviewType(path.match(/\.html?$/) ? 'html' : 'text')
    } catch { toast.error('Could not read file') }
  }

  const hasMessages = messages.length > 0
  const lastAgentMsg = [...messages].reverse().find(m => m.role === 'agent')

  return (
    <>
      <div className="chat-area" ref={dropRef}>
        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-inner">
            {!hasMessages && !isStreaming ? (
              <WelcomeScreen onSuggestion={handleSuggestion} onToggleWs={() => setShowWorkspace(!showWorkspace)} />
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
                        {/* Show attached files */}
                        {msg.attachments?.length > 0 && (
                          <div className="tools-row">
                            {msg.attachments.map((f, i) => (
                              <span key={i} className="tool-pill">
                                <FileText size={11} /> {f.filename}
                              </span>
                            ))}
                          </div>
                        )}
                        {/* Show agent actions (bash commands, code execution) */}
                        {msg.actions?.length > 0 && (
                          <div style={{ marginBottom: 10 }}>
                            {msg.actions.map((a, i) => (
                              <AgentAction key={i} action={a} />
                            ))}
                          </div>
                        )}
                        {/* Show tool call pills */}
                        {msg.toolCalls?.length > 0 && !msg.actions?.length && (
                          <div className="tools-row">
                            {msg.toolCalls.map((tc, i) => (
                              <span key={i} className="tool-pill">
                                <ToolIcon name={tc.tool} /> {tc.tool}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="msg-text"><RenderContent content={msg.content} /></div>
                      </div>
                    </div>
                    {msg.role === 'agent' && msg.id === lastAgentMsg?.id && !feedback[msg.id] && !isStreaming && (
                      <div className="feedback-bar">
                        <span className="feedback-label">Was this task successful?</span>
                        <button className="feedback-btn yes" onClick={() => handleFeedback(msg.id, 'yes')}><ThumbsUp size={13} /> Yes</button>
                        <button className="feedback-btn no" onClick={() => handleFeedback(msg.id, 'no')}><ThumbsDown size={13} /> No</button>
                        <button className="feedback-btn keep" onClick={() => handleFeedback(msg.id, 'keep')}><RotateCcw size={13} /> Keep working</button>
                      </div>
                    )}
                  </div>
                ))}

                {/* Streaming in progress */}
                {isStreaming && (
                  <div className="msg">
                    <div className="msg-avatar agent"><Bot size={14} /></div>
                    <div className="msg-body">
                      <div className="msg-role">Arena</div>
                      {/* Show streaming actions */}
                      {streamingActions.length > 0 && (
                        <div style={{ marginBottom: 10 }}>
                          {streamingActions.map((a, i) => (
                            <AgentAction key={i} action={a} />
                          ))}
                        </div>
                      )}
                      {/* Show streaming text or thinking dots */}
                      {streamingContent ? (
                        <div className="msg-text"><RenderContent content={streamingContent} /></div>
                      ) : (
                        <div className="thinking">
                          <div className="thinking-dots">
                            <div className="thinking-dot" /><div className="thinking-dot" /><div className="thinking-dot" />
                          </div>
                          Thinking…
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Input bar */}
        <div className="input-area">
          {/* Attached files preview */}
          {attachedFiles.length > 0 && (
            <div style={{ maxWidth: 768, margin: '0 auto 8px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {attachedFiles.map((f, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '4px 10px', background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)', borderRadius: 6, fontSize: 11,
                }}>
                  <FileText size={12} /> {f.filename}
                  <button onClick={() => setAttachedFiles(prev => prev.filter((_, j) => j !== i))} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }}>
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

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
              <input ref={fileInputRef} type="file" multiple style={{ display: 'none' }} onChange={handleFileInputChange}
                accept=".png,.jpg,.jpeg,.webp,.gif,.pdf,.txt,.md,.csv,.html,.css,.js,.json,.xml,.py,.ts,.sh,.yaml,.sql" />
              <button type="button" className="input-action" style={{ padding: 6 }} onClick={() => fileInputRef.current?.click()}>
                <Paperclip size={16} />
              </button>
              <button type="submit" className="input-send" disabled={!input.trim() || isStreaming}>
                <Send size={15} />
              </button>
            </div>
            <div className="input-bottom">
              <button type="button" className="input-action" onClick={() => fileInputRef.current?.click()}>
                <Paperclip size={13} /> Add files
              </button>
              <button type="button" className="input-action" onClick={() => setShowWorkspace(!showWorkspace)}>
                <PanelRightOpen size={13} /> Files
              </button>
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
            <div style={{ display: 'flex', gap: 4 }}>
              <button className="ws-close" onClick={() => setShowWorkspace(false)}><X size={16} /></button>
            </div>
          </div>
          <div className="ws-tabs">
            {['files', 'preview'].map(t => (
              <button key={t} className={`ws-tab${wsTab === t ? ' active' : ''}`} onClick={() => setWsTab(t)}>{t}</button>
            ))}
          </div>
          <div className="ws-body">
            {wsTab === 'files' && <FilesPanel onSelect={openFile} selected={selectedFile} />}
            {wsTab === 'preview' && (
              selectedFile ? (
                <div className="ws-preview">
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, display: 'flex', justifyContent: 'space-between' }}>
                    <span>{selectedFile}</span>
                  </div>
                  {filePreviewType === 'html' ? (
                    <iframe className="ws-preview-iframe" srcDoc={fileContent} title="Preview" sandbox="allow-scripts" />
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

/* ── Agent Action Display (bash, code, etc.) ─────────────────── */

function AgentAction({ action }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = action.tool === 'shell' || action.tool === 'bash' ? Terminal
    : action.tool === 'execute_code' ? Code2
    : action.tool === 'web_search' ? Search
    : Wrench

  const statusColor = action.status === 'success' ? 'var(--green)'
    : action.status === 'error' ? 'var(--red)'
    : 'var(--yellow)'

  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 8, marginBottom: 6, overflow: 'hidden',
    }}>
      <div onClick={() => setExpanded(!expanded)} style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
        cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)',
      }}>
        <Icon size={13} style={{ color: 'var(--purple)' }} />
        <span style={{ flex: 1, fontFamily: 'var(--font-mono)', textTransform: 'lowercase' }}>
          {action.display || action.tool}
        </span>
        {action.status === 'running' ? (
          <div className="thinking-dots" style={{ gap: 2 }}>
            <div className="thinking-dot" style={{ width: 4, height: 4 }} />
            <div className="thinking-dot" style={{ width: 4, height: 4 }} />
            <div className="thinking-dot" style={{ width: 4, height: 4 }} />
          </div>
        ) : (
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
        )}
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </div>
      {expanded && action.result && (
        <pre style={{
          margin: 0, padding: '8px 12px', borderTop: '1px solid var(--border)',
          fontSize: 11, fontFamily: 'var(--font-mono)', whiteSpace: 'pre-wrap',
          wordBreak: 'break-all', color: 'var(--text-secondary)', maxHeight: 200,
          overflow: 'auto', lineHeight: 1.5,
        }}>
          {typeof action.result === 'string' ? action.result : JSON.stringify(action.result, null, 2)}
        </pre>
      )}
    </div>
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
  return <>{tree.map(n => <TreeNode key={n.path} node={n} depth={0} onSelect={onSelect} selected={selected} />)}</>
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
      {expanded && node.children?.map(c => <TreeNode key={c.path} node={c} depth={depth + 1} onSelect={onSelect} selected={selected} />)}
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

/* ── Welcome Screen ──────────────────────────────────────────── */

function WelcomeScreen({ onSuggestion, onToggleWs }) {
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
        {suggestions.map(s => (
          <div key={s.title} className="welcome-card" onClick={() => onSuggestion(s.title)}>
            <div className="welcome-card-title">{s.title}</div>
            {s.desc}
          </div>
        ))}
      </div>
      <div className="welcome-footer">
        <Paperclip size={12} /> Drop files… Add files
      </div>
      <button className="welcome-github">
        <Github size={14} /> Connect your GitHub <span className="welcome-new-badge">NEW</span>
      </button>
      <button className="input-action" onClick={onToggleWs} style={{ marginTop: 16 }}>
        <PanelRightOpen size={14} /> Toggle Workspace
      </button>
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
