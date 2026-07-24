import { useState, useRef, useEffect, useCallback } from 'react'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  Send, Bot, User, Paperclip, Wrench, Play, CheckCircle2,
  XCircle, FolderOpen, FileText, Terminal, Search, Code2,
  Trash2, Plus, Copy, Loader2,
} from 'lucide-react'
import { agentApi } from '../api/agent'
import { apiErrorMessage } from '../api/client'

export default function SessionsPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, isThinking, scrollToBottom])

  const chatMutation = useMutation({
    mutationFn: (message) => agentApi.chat(message),
    onMutate: (message) => {
      setIsThinking(true)
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: 'user', content: message, timestamp: new Date() },
      ])
      setInput('')
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: data.response,
          toolCalls: data.tool_calls || [],
          thinking: data.thinking,
          modelUsed: data.model_used,
          timestamp: new Date(),
        },
      ])
      setIsThinking(false)
    },
    onError: (e) => {
      toast.error(apiErrorMessage(e))
      setIsThinking(false)
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: `Error: ${apiErrorMessage(e)}`,
          error: true,
          timestamp: new Date(),
        },
      ])
    },
  })

  function handleSubmit(e) {
    e.preventDefault()
    if (!input.trim() || isThinking) return
    chatMutation.mutate(input.trim())
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  function handleClear() {
    setMessages([])
  }

  function handleSuggestion(text) {
    setInput(text)
    setTimeout(() => {
      chatMutation.mutate(text)
    }, 50)
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {/* Messages area */}
      <div className="chat-messages">
        {messages.length === 0 && !isThinking && (
          <WelcomeScreen onSuggestion={handleSuggestion} />
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}

        {isThinking && (
          <div className="chat-message">
            <div className="chat-message-avatar assistant">
              <Bot size={14} />
            </div>
            <div className="chat-message-content">
              <div className="chat-message-role">Arena</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 0' }}>
                <Loader2 size={16} style={{ color: 'var(--accent-blue)', animation: 'spin 1s linear infinite' }} />
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Thinking…</span>
              </div>
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="chat-input-container">
        {messages.length > 0 && (
          <div style={{ maxWidth: 800, margin: '0 auto', marginBottom: 8, display: 'flex', justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost btn-sm" onClick={handleClear} style={{ fontSize: 11 }}>
              <Trash2 size={12} /> Clear chat
            </button>
          </div>
        )}
        <form className="chat-input-wrapper" onSubmit={handleSubmit}>
          <div className="chat-input-top">
            <textarea
              ref={textareaRef}
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Arena to do anything…"
              rows={1}
              disabled={isThinking}
              style={{ height: 'auto' }}
              onInput={(e) => {
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
              }}
            />
            <button type="submit" className="chat-input-send" disabled={!input.trim() || isThinking}>
              <Send size={16} />
            </button>
          </div>
          <div className="chat-input-bottom">
            <button type="button" className="chat-input-action">
              <Paperclip size={13} /> Attach
            </button>
            <button type="button" className="chat-input-action">
              <Wrench size={13} /> Tools
            </button>
            <div className="chat-input-model">
              <Bot size={12} /> Arena Agent · Local Model
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ── Welcome Screen ────────────────────────────────────────────── */

function WelcomeScreen({ onSuggestion }) {
  const suggestions = [
    { icon: FileText, text: 'Read the README.md file', prompt: 'Read the README.md file' },
    { icon: Code2, text: 'Write a Python fibonacci function', prompt: 'Write a Python function to calculate fibonacci numbers' },
    { icon: FolderOpen, text: 'List all files in the project', prompt: 'List all files in the current directory' },
    { icon: Play, text: 'Run Python code', prompt: 'Run this Python code: ```python\nprint("Hello from Arena!")\nfor i in range(5):\n    print(f"Step {i+1}")\n```' },
    { icon: Terminal, text: 'Check system info', prompt: 'Show me the system information' },
    { icon: Search, text: 'Search the web', prompt: 'Search for Python best practices 2024' },
  ]

  return (
    <div className="chat-welcome">
      <div className="chat-welcome-icon">
        <Bot size={32} color="white" />
      </div>
      <h2>Arena Agent</h2>
      <p>
        I'm your autonomous AI agent. I can read files, write code, execute
        programs, manage your workspace, and search the web — automatically.
      </p>

      <div className="chat-welcome-suggestions">
        {suggestions.map((s) => {
          const Icon = s.icon
          return (
            <div
              key={s.text}
              className="chat-welcome-suggestion"
              onClick={() => onSuggestion(s.prompt)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Icon size={16} style={{ color: 'var(--accent-blue)', flexShrink: 0 }} />
                <h4>{s.text}</h4>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── Chat Message ──────────────────────────────────────────────── */

function ChatMessage({ message }) {
  const isUser = message.role === 'user'
  const [showThinking, setShowThinking] = useState(false)
  const [copiedCode, setCopiedCode] = useState(null)

  function copyCode(code) {
    navigator.clipboard.writeText(code)
    setCopiedCode(code)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  return (
    <div className="chat-message">
      <div className={`chat-message-avatar ${isUser ? 'user' : 'assistant'}`}>
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div className="chat-message-content">
        <div className="chat-message-role">
          {isUser ? 'You' : 'Arena'}
          <span className="time">
            {message.timestamp?.toLocaleTimeString?.() || ''}
          </span>
          {message.modelUsed && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)', background: 'var(--bg-tertiary)', padding: '1px 6px', borderRadius: 4 }}>
              {message.modelUsed}
            </span>
          )}
        </div>

        {/* Tool calls */}
        {message.toolCalls?.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            {message.toolCalls.map((tc, i) => (
              <ToolCallDisplay key={i} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Thinking toggle */}
        {message.thinking && (
          <div style={{ marginBottom: 8 }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setShowThinking(!showThinking)}
              style={{ fontSize: 11, padding: '2px 8px' }}
            >
              {showThinking ? 'Hide' : 'Show'} reasoning
            </button>
            {showThinking && (
              <div style={{
                marginTop: 4, padding: '8px 12px',
                background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-primary)',
                fontSize: 12, fontFamily: 'var(--font-mono)',
                color: 'var(--text-muted)', whiteSpace: 'pre-wrap',
              }}>
                {message.thinking}
              </div>
            )}
          </div>
        )}

        {/* Main response */}
        <div className={`chat-message-text${message.error ? ' error' : ''}`}>
          <MessageContent content={message.content} onCopyCode={copyCode} />
        </div>
      </div>
    </div>
  )
}

/* ── Tool Call Display ──────────────────────────────────────────── */

const TOOL_ICONS = {
  read_file: FileText,
  write_file: FileText,
  list_files: FolderOpen,
  delete_file: Trash2,
  execute_code: Code2,
  run_code: Code2,
  shell: Terminal,
  bash: Terminal,
  terminal: Terminal,
  command: Terminal,
  web_search: Search,
  search: Search,
  install: Wrench,
  system_info: Wrench,
}

function ToolCallDisplay({ toolCall }) {
  const [expanded, setExpanded] = useState(false)
  const Icon = TOOL_ICONS[toolCall.tool] || Wrench
  const success = toolCall.success

  return (
    <div className="tool-call">
      <div className="tool-call-header" onClick={() => setExpanded(!expanded)}>
        <Icon size={14} className="tool-icon" />
        <span style={{ flex: 1 }}>{toolCall.tool}</span>
        {success ? (
          <CheckCircle2 size={14} style={{ color: 'var(--accent-green)' }} />
        ) : (
          <XCircle size={14} style={{ color: 'var(--accent-red)' }} />
        )}
      </div>
      {expanded && (
        <>
          {Object.keys(toolCall.arguments || {}).length > 0 && (
            <div className="tool-call-body">
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Arguments</div>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {JSON.stringify(toolCall.arguments, null, 2)}
              </pre>
            </div>
          )}
          <div className={`tool-call-result ${success ? 'success' : 'error'}`}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>Result</div>
            <pre style={{
              margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              fontSize: 12, maxHeight: 300, overflow: 'auto',
              color: success ? 'var(--text-primary)' : 'var(--accent-red)',
            }}>
              {typeof toolCall.result === 'string' ? toolCall.result : JSON.stringify(toolCall.result, null, 2)}
            </pre>
          </div>
        </>
      )}
    </div>
  )
}

/* ── Message Content Renderer ───────────────────────────────────── */

function MessageContent({ content, onCopyCode }) {
  if (!content) return null

  // Split by code blocks
  const parts = content.split(/(```[\s\S]*?```)/g)

  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).split('\n')
          const lang = lines[0].trim()
          const code = lang ? lines.slice(1).join('\n') : lines.slice(1).join('\n') || lines.join('\n')
          return (
            <div key={i} style={{ margin: '12px 0' }}>
              <div className="code-header">
                <span>{lang || 'code'}</span>
                <button className="code-copy-btn" onClick={() => onCopyCode?.(code)}>
                  <Copy size={11} /> {copiedCode === code ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <pre><code>{code}</code></pre>
            </div>
          )
        }

        // Inline formatting
        return (
          <span key={i}>
            {part.split('\n').map((line, j) => (
              <span key={j}>
                {j > 0 && <br />}
                <InlineContent text={line} />
              </span>
            ))}
          </span>
        )
      })}
    </>
  )
}

function InlineContent({ text }) {
  // Bold
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')

  return <span dangerouslySetInnerHTML={{ __html: text }} />
}
