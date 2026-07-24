import { useState, useRef, useEffect, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Send, Bot, User, Plus, Paperclip, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, Copy, Loader2, FileText, FolderOpen,
  Code2, Terminal, Search, Wrench, Trash2, Download, X,
} from 'lucide-react'
import { agentApi } from '../api/agent'
import { workspaceApi } from '../api/workspace'
import { apiErrorMessage } from '../api/client'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [showWorkspace, setShowWorkspace] = useState(false)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)

  // Listen for new chat event from nav
  useEffect(() => {
    const handler = () => { setMessages([]); setShowWorkspace(false) }
    window.addEventListener('arena-new-chat', handler)
    return () => window.removeEventListener('arena-new-chat', handler)
  }, [])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, isThinking, scrollToBottom])

  const chatMutation = useMutation({
    mutationFn: (msg) => agentApi.chat(msg),
    onMutate: (msg) => {
      setIsThinking(true)
      setMessages((prev) => [...prev, {
        id: Date.now(), role: 'user', content: msg, timestamp: new Date(),
      }])
      setInput('')
      if (textareaRef.current) textareaRef.current.style.height = 'auto'
    },
    onSuccess: (data) => {
      setMessages((prev) => [...prev, {
        id: Date.now() + 1, role: 'assistant',
        content: data.response, toolCalls: data.tool_calls || [],
        thinking: data.thinking, timestamp: new Date(),
      }])
      setIsThinking(false)
      // Show workspace if tools were used
      if (data.tool_calls?.length > 0) setShowWorkspace(true)
    },
    onError: (e) => {
      toast.error(apiErrorMessage(e))
      setIsThinking(false)
    },
  })

  function handleSubmit(e) {
    e?.preventDefault()
    if (!input.trim() || isThinking) return
    chatMutation.mutate(input.trim())
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  function handleFileUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    // Add file info to input
    setInput((prev) => prev + `\n[Attached: ${file.name}]`)
    e.target.value = ''
  }

  const hasMessages = messages.length > 0

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Main chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        {/* Messages or Welcome */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {!hasMessages && !isThinking ? (
            <WelcomeScreen onSubmit={(text) => { setInput(text); chatMutation.mutate(text) }} />
          ) : (
            <div style={{ maxWidth: 800, margin: '0 auto', padding: '24px 20px' }}>
              {messages.map((msg) => (
                <Message key={msg.id} message={msg} />
              ))}
              {isThinking && <ThinkingIndicator />}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input bar */}
        <div style={{ padding: '12px 20px 24px', flexShrink: 0 }}>
          <form onSubmit={handleSubmit} style={{
            maxWidth: 800, margin: '0 auto',
            background: 'var(--bg-input)',
            border: '1px solid var(--border-primary)',
            borderRadius: 16,
            overflow: 'hidden',
            transition: 'border-color 0.15s',
          }}
          onFocus={(e) => e.currentTarget.style.borderColor = 'var(--border-focus)'}
          onBlur={(e) => e.currentTarget.style.borderColor = 'var(--border-primary)'}
          >
            <div style={{ display: 'flex', alignItems: 'flex-end', padding: '12px 16px', gap: 8 }}>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="What would you like to do?"
                disabled={isThinking}
                rows={1}
                style={{
                  flex: 1, background: 'transparent', border: 'none', outline: 'none',
                  color: 'var(--text-primary)', fontSize: 14, fontFamily: 'var(--font-sans)',
                  resize: 'none', minHeight: 24, maxHeight: 200, lineHeight: 1.5,
                }}
                onInput={(e) => {
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
                }}
              />
              <button type="button" onClick={() => fileInputRef.current?.click()} style={{
                width: 32, height: 32, borderRadius: 8, background: 'transparent',
                border: 'none', color: 'var(--text-muted)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Paperclip size={18} />
              </button>
              <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={handleFileUpload} />
              <button type="submit" disabled={!input.trim() || isThinking} style={{
                width: 32, height: 32, borderRadius: 8,
                background: input.trim() && !isThinking ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                border: 'none', color: 'white', cursor: input.trim() && !isThinking ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s',
              }}>
                <Send size={16} />
              </button>
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 16px', borderTop: '1px solid var(--border-subtle)',
              fontSize: 11, color: 'var(--text-muted)',
            }}>
              <span>Add files</span>
              <span style={{ marginLeft: 'auto' }}>
                Inputs are processed by AI and responses may be inaccurate.
              </span>
            </div>
          </form>
        </div>
      </div>

      {/* Workspace panel — shows when tools are used */}
      {showWorkspace && <WorkspacePanel onClose={() => setShowWorkspace(false)} />}
    </div>
  )
}

/* ── Welcome Screen ──────────────────────────────────────────── */

function WelcomeScreen({ onSubmit }) {
  const suggestions = [
    'Create a landing page with HTML and CSS',
    'Build a Python script that scrapes a website',
    'Write a todo app in JavaScript',
    'Analyze the files in this project',
    'Create a REST API with FastAPI',
    'Build a React component for a login form',
  ]

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', minHeight: '100%', padding: 48,
    }}>
      <div style={{
        width: 64, height: 64, borderRadius: 20,
        background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        marginBottom: 28, boxShadow: '0 0 40px rgba(74, 158, 255, 0.2)',
      }}>
        <Bot size={32} color="white" />
      </div>

      <h1 style={{
        fontSize: 32, fontWeight: 700, marginBottom: 8,
        background: 'linear-gradient(135deg, var(--text-primary), var(--text-secondary))',
        WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
      }}>
        What would you like to do?
      </h1>
      <p style={{ fontSize: 15, color: 'var(--text-muted)', marginBottom: 40, maxWidth: 500, textAlign: 'center', lineHeight: 1.6 }}>
        Arena can build apps, write code, research topics, create files,
        and complete multi-step tasks — all from a single prompt.
      </p>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: 10, maxWidth: 750, width: '100%',
      }}>
        {suggestions.map((s) => (
          <button key={s} onClick={() => onSubmit(s)} style={{
            background: 'var(--bg-secondary)', border: '1px solid var(--border-primary)',
            borderRadius: 12, padding: '14px 16px', textAlign: 'left',
            color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer',
            transition: 'all 0.15s', lineHeight: 1.4,
          }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--border-focus)'; e.currentTarget.style.background = 'var(--bg-tertiary)' }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border-primary)'; e.currentTarget.style.background = 'var(--bg-secondary)' }}
          >
            {s}
          </button>
        ))}
      </div>

      <div style={{
        marginTop: 32, display: 'flex', alignItems: 'center', gap: 8,
        fontSize: 11, color: 'var(--text-muted)',
      }}>
        <Paperclip size={12} /> Drop files to attach
      </div>
    </div>
  )
}

/* ── Message ─────────────────────────────────────────────────── */

function Message({ message }) {
  const isUser = message.role === 'user'
  const [showThinking, setShowThinking] = useState(false)

  return (
    <div style={{
      display: 'flex', gap: 12, padding: '16px 0',
      animation: 'msg-in 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
    }}>
      <style>{`@keyframes msg-in { from { opacity: 0; transform: translateY(8px); } }`}</style>
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0, marginTop: 2,
        background: isUser
          ? 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))'
          : 'linear-gradient(135deg, var(--accent-green), var(--accent-blue))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isUser ? <User size={14} color="white" /> : <Bot size={14} color="white" />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          {isUser ? 'You' : 'Arena'}
          <span style={{ fontWeight: 400, color: 'var(--text-muted)', fontSize: 11 }}>
            {message.timestamp?.toLocaleTimeString?.()}
          </span>
        </div>

        {/* Tool calls */}
        {message.toolCalls?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            {message.toolCalls.map((tc, i) => <ToolCall key={i} tc={tc} />)}
          </div>
        )}

        {/* Thinking */}
        {message.thinking && (
          <div style={{ marginBottom: 8 }}>
            <button onClick={() => setShowThinking(!showThinking)} style={{
              background: 'transparent', border: 'none', color: 'var(--text-muted)',
              fontSize: 11, cursor: 'pointer', padding: 0,
            }}>
              {showThinking ? '▾' : '▸'} Reasoning
            </button>
            {showThinking && (
              <pre style={{
                marginTop: 4, padding: 12, background: 'var(--bg-tertiary)',
                borderRadius: 8, fontSize: 12, fontFamily: 'var(--font-mono)',
                color: 'var(--text-muted)', whiteSpace: 'pre-wrap',
                border: '1px solid var(--border-primary)',
                maxHeight: 200, overflow: 'auto',
              }}>
                {message.thinking}
              </pre>
            )}
          </div>
        )}

        {/* Response text */}
        <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-primary)' }}>
          <RenderContent content={message.content} />
        </div>
      </div>
    </div>
  )
}

/* ── Thinking Indicator ──────────────────────────────────────── */

function ThinkingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 12, padding: '16px 0' }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
        background: 'linear-gradient(135deg, var(--accent-green), var(--accent-blue))',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Bot size={14} color="white" />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Loader2 size={16} style={{ color: 'var(--accent-blue)', animation: 'spin 1s linear infinite' }} />
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Thinking…</span>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

/* ── Tool Call Display ───────────────────────────────────────── */

const TOOL_ICONS = {
  read_file: FileText, write_file: FileText, list_files: FolderOpen,
  delete_file: Trash2, execute_code: Code2, run_code: Code2,
  shell: Terminal, bash: Terminal, command: Terminal,
  web_search: Search, search: Search, install: Wrench,
}

function ToolCall({ tc }) {
  const [open, setOpen] = useState(false)
  const Icon = TOOL_ICONS[tc.tool] || Wrench

  return (
    <div style={{
      background: 'var(--bg-tertiary)', border: '1px solid var(--border-primary)',
      borderRadius: 8, marginBottom: 6, overflow: 'hidden',
    }}>
      <div onClick={() => setOpen(!open)} style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
        cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)',
      }}>
        <Icon size={13} style={{ color: 'var(--accent-purple)' }} />
        <span style={{ flex: 1, fontWeight: 500 }}>{tc.tool}</span>
        {tc.success
          ? <CheckCircle2 size={13} style={{ color: 'var(--accent-green)' }} />
          : <XCircle size={13} style={{ color: 'var(--accent-red)' }} />
        }
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
      </div>
      {open && (
        <div style={{ borderTop: '1px solid var(--border-primary)', padding: 12 }}>
          {Object.keys(tc.arguments || {}).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>Arguments</div>
              <pre style={{
                margin: 0, padding: 8, background: 'var(--bg-code)',
                borderRadius: 4, fontSize: 11, fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                color: 'var(--text-secondary)',
              }}>
                {JSON.stringify(tc.arguments, null, 2)}
              </pre>
            </div>
          )}
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>Result</div>
            <pre style={{
              margin: 0, padding: 8, background: 'var(--bg-code)',
              borderRadius: 4, fontSize: 11, fontFamily: 'var(--font-mono)',
              whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              color: tc.success ? 'var(--text-primary)' : 'var(--accent-red)',
              maxHeight: 300, overflow: 'auto',
            }}>
              {typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2)}
            </pre>
          </div>
        </div>
      )}
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
      return (
        <div key={i} style={{ margin: '12px 0' }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '6px 12px', background: 'var(--bg-tertiary)',
            borderBottom: '1px solid var(--border-primary)',
            borderRadius: '8px 8px 0 0', fontSize: 11, color: 'var(--text-muted)',
          }}>
            <span>{lang || 'code'}</span>
            <button onClick={() => navigator.clipboard.writeText(code)} style={{
              background: 'transparent', border: '1px solid var(--border-primary)',
              borderRadius: 4, padding: '2px 8px', fontSize: 10,
              color: 'var(--text-muted)', cursor: 'pointer',
            }}>
              <Copy size={10} style={{ marginRight: 3 }} />Copy
            </button>
          </div>
          <pre style={{
            margin: 0, padding: 14, background: 'var(--bg-code)',
            border: '1px solid var(--border-primary)', borderTop: 'none',
            borderRadius: '0 0 8px 8px', overflow: 'auto',
            fontSize: 13, lineHeight: 1.5, fontFamily: 'var(--font-mono)',
          }}>
            <code>{code}</code>
          </pre>
        </div>
      )
    }

    // Inline text with line breaks
    return (
      <span key={i}>
        {part.split('\n').map((line, j) => (
          <span key={j}>{j > 0 && <br />}{renderInline(line)}</span>
        ))}
      </span>
    )
  })
}

function renderInline(text) {
  // Bold
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code style="background:var(--bg-code);padding:2px 5px;border-radius:4px;font-size:13px;font-family:var(--font-mono)">$1</code>')
  return <span dangerouslySetInnerHTML={{ __html: text }} />
}

/* ── Workspace Panel ─────────────────────────────────────────── */

function WorkspacePanel({ onClose }) {
  const [tab, setTab] = useState('files')
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState('')

  const { data: tree, refetch } = useQuery({
    queryKey: ['workspace', 'tree'],
    queryFn: () => workspaceApi.tree(),
    staleTime: 5_000,
    refetchInterval: 10_000,
  })

  async function openFile(path) {
    try {
      const data = await workspaceApi.readFile(path)
      setSelectedFile(path)
      setFileContent(data.content)
    } catch (e) {
      toast.error('Could not read file')
    }
  }

  return (
    <div style={{
      width: 340, background: 'var(--bg-secondary)',
      borderLeft: '1px solid var(--border-secondary)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '10px 14px', borderBottom: '1px solid var(--border-secondary)',
      }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Workspace</span>
        <div style={{ display: 'flex', gap: 4 }}>
          <button onClick={() => refetch()} style={{
            background: 'transparent', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', padding: 4,
          }}>
            <FolderOpen size={14} />
          </button>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', padding: 4,
          }}>
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', gap: 2, padding: '6px 10px',
        borderBottom: '1px solid var(--border-secondary)',
      }}>
        {['files', 'preview'].map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '5px 12px', borderRadius: 6, border: 'none',
            background: tab === t ? 'var(--bg-active)' : 'transparent',
            color: tab === t ? 'var(--text-primary)' : 'var(--text-muted)',
            fontSize: 12, cursor: 'pointer', textTransform: 'capitalize',
          }}>
            {t}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
        {tab === 'files' && (
          <div>
            {tree?.map((node) => (
              <TreeNode key={node.path} node={node} depth={0} onSelect={openFile} selected={selectedFile} />
            ))}
            {(!tree || tree.length === 0) && (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                Files created by the agent will appear here
              </div>
            )}
          </div>
        )}
        {tab === 'preview' && (
          <div>
            {selectedFile ? (
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, padding: '0 4px' }}>
                  {selectedFile}
                </div>
                <pre style={{
                  margin: 0, padding: 12, background: 'var(--bg-code)',
                  borderRadius: 8, fontSize: 12, fontFamily: 'var(--font-mono)',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  color: 'var(--text-primary)', lineHeight: 1.5,
                  maxHeight: '100%', overflow: 'auto',
                  border: '1px solid var(--border-primary)',
                }}>
                  {fileContent}
                </pre>
              </div>
            ) : (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>
                Click a file to preview
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function TreeNode({ node, depth, onSelect, selected }) {
  const [expanded, setExpanded] = useState(depth < 2)
  const indent = depth * 12

  if (node.is_dir) {
    return (
      <div>
        <div onClick={() => setExpanded(!expanded)} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '5px 8px', paddingLeft: 8 + indent,
          fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
          borderRadius: 4,
        }}>
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <FolderOpen size={13} style={{ color: 'var(--accent-yellow)', opacity: 0.7 }} />
          <span>{node.name}</span>
        </div>
        {expanded && node.children?.map((c) => (
          <TreeNode key={c.path} node={c} depth={depth + 1} onSelect={onSelect} selected={selected} />
        ))}
      </div>
    )
  }

  const ext = node.name.split('.').pop()?.toLowerCase()
  const colors = { py: '#3572A5', js: '#f1e05a', ts: '#3178c6', json: '#666', md: '#22c55e', html: '#e34c26', css: '#563d7c' }

  return (
    <div onClick={() => onSelect(node.path)} style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '5px 8px', paddingLeft: 8 + indent,
      fontSize: 12, cursor: 'pointer', borderRadius: 4,
      color: selected === node.path ? 'var(--text-primary)' : 'var(--text-secondary)',
      background: selected === node.path ? 'var(--bg-active)' : 'transparent',
    }}>
      <span style={{ fontSize: 9, fontWeight: 700, width: 16, textAlign: 'center', color: colors[ext] || '#666' }}>
        {ext?.toUpperCase().slice(0, 2) || '·'}
      </span>
      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{node.name}</span>
    </div>
  )
}
