import { useState, useRef, useEffect, useCallback, memo } from 'react'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Send, Bot, User, ChevronDown, Hammer, Brain } from 'lucide-react'
import { agentApi } from '../api/agent'
import { apiErrorMessage } from '../api/client'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const messagesRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    const handler = () => { setMessages([]) }
    window.addEventListener('arena-new-chat', handler)
    return () => window.removeEventListener('arena-new-chat', handler)
  }, [])

  const scrollToBottom = useCallback((smooth = true) => {
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
  }, [])

  useEffect(() => { scrollToBottom(false) }, [messages.length])

  useEffect(() => {
    const el = messagesRef.current
    if (!el) return
    function handleScroll() {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100
      setShowScrollBtn(!atBottom)
    }
    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])

  const chatMutation = useMutation({
    mutationFn: (msg) => agentApi.chat(msg),
    onMutate: (msg) => {
      setIsStreaming(true)
      setMessages((prev) => [...prev, { id: Date.now(), role: 'user', content: msg, created_at: new Date().toISOString() }])
      setInput('')
    },
    onSuccess: (data) => {
      setMessages((prev) => [...prev, {
        id: Date.now() + 1, role: 'agent', content: data.response,
        tool_calls: data.tool_calls?.map((tc) => ({
          tool_name: tc.tool, tool_call_id: `${tc.tool}-${Date.now()}`,
          created_at: new Date().toISOString(),
        })) || [],
        extra_data: data.thinking ? { reasoning_steps: [{ title: 'Analyzed request', action: 'think' }] } : null,
        created_at: new Date().toISOString(),
      }])
      setIsStreaming(false)
    },
    onError: (e) => {
      toast.error(apiErrorMessage(e))
      setIsStreaming(false)
    },
  })

  function handleSubmit() {
    if (!input.trim() || isStreaming) return
    chatMutation.mutate(input.trim())
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <>
      <div className="chat-messages" ref={messagesRef}>
        <div className="chat-messages-inner">
          <Messages messages={messages} isStreaming={isStreaming} />
        </div>
      </div>

      {showScrollBtn && (
        <button className="scroll-to-bottom" onClick={() => scrollToBottom()}>
          <ChevronDown size={16} />
        </button>
      )}

      <div className="chat-input-container">
        <div className="chat-input-wrapper">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="Ask anything"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            rows={1}
            onInput={(e) => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
            }}
          />
          <button
            className="chat-send-btn"
            onClick={handleSubmit}
            disabled={!input.trim() || isStreaming}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </>
  )
}

/* ── Messages ────────────────────────────────────────────────── */

function Messages({ messages, isStreaming }) {
  if (messages.length === 0) {
    return <ChatBlankState />
  }

  return (
    <>
      {messages.map((msg, i) => {
        if (msg.role === 'agent') {
          return <AgentMessageWrapper key={msg.id || i} message={msg} />
        }
        return <UserMessage key={msg.id || i} message={msg} />
      })}
      {isStreaming && <ThinkingLoader />}
    </>
  )
}

/* ── Agent Message (with tool calls + reasoning) ─────────────── */

function AgentMessageWrapper({ message }) {
  return (
    <div className="agent-message-wrapper">
      {/* Reasoning steps */}
      {message.extra_data?.reasoning_steps?.length > 0 && (
        <div className="reasoning-row">
          <div className="tool-icon-wrapper">
            <Brain size={14} />
          </div>
          <div className="reasoning-steps">
            <p className="reasoning-label">Reasoning</p>
            {message.extra_data.reasoning_steps.map((step, i) => (
              <div key={i} className="reasoning-step">
                <div className="reasoning-step-badge">STEP {i + 1}</div>
                <span className="reasoning-step-text">{step.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tool calls */}
      {message.tool_calls?.length > 0 && (
        <div className="tool-calls-row">
          <div className="tool-icon-wrapper">
            <Hammer size={14} />
          </div>
          <div className="tool-calls-list">
            {message.tool_calls.map((tc, i) => (
              <div key={tc.tool_call_id || i} className="tool-pill">
                {tc.tool_name}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main content */}
      <AgentMessage message={message} />
    </div>
  )
}

/* ── Agent Message Content ───────────────────────────────────── */

const AgentMessage = memo(function AgentMessage({ message }) {
  return (
    <div className="message">
      <div className="message-avatar agent">
        <Bot size={14} />
      </div>
      <div className="message-content">
        <MarkdownRenderer content={message.content} />
      </div>
    </div>
  )
})

/* ── User Message ────────────────────────────────────────────── */

const UserMessage = memo(function UserMessage({ message }) {
  return (
    <div className="message">
      <div className="message-avatar user">
        <User size={14} />
      </div>
      <div className="message-content">
        {message.content}
      </div>
    </div>
  )
})

/* ── Thinking Loader ─────────────────────────────────────────── */

function ThinkingLoader() {
  return (
    <div className="message">
      <div className="message-avatar agent">
        <Bot size={14} />
      </div>
      <div className="thinking-loader">
        <div className="thinking-dot" />
        <div className="thinking-dot" />
        <div className="thinking-dot" />
      </div>
    </div>
  )
}

/* ── Blank State ─────────────────────────────────────────────── */

function ChatBlankState() {
  function handleAction(text) {
    window.dispatchEvent(new CustomEvent('arena-new-chat'))
    setTimeout(() => {
      const input = document.querySelector('.chat-input')
      if (input) {
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set
        nativeInputValueSetter.call(input, text)
        input.dispatchEvent(new Event('input', { bubbles: true }))
      }
    }, 50)
  }

  return (
    <div className="blank-state">
      <div style={{ marginBottom: 16 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 12,
          background: 'var(--brand)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          margin: '0 auto',
        }}>
          <Bot size={24} color="white" />
        </div>
      </div>
      <h1>What would you like to do?</h1>
      <p>
        Arena can build apps, write code, research topics, create files,
        and complete multi-step tasks — all from a single prompt.
      </p>
      <div className="blank-state-actions">
        <button className="blank-state-btn primary" onClick={() => handleAction('Create a landing page')}>
          Create a landing page
        </button>
        <button className="blank-state-btn primary" onClick={() => handleAction('Build a Python script')}>
          Build a Python script
        </button>
        <button className="blank-state-btn secondary">
          Explore use cases
        </button>
      </div>
    </div>
  )
}

/* ── Markdown Renderer (minimal) ─────────────────────────────── */

function MarkdownRenderer({ content }) {
  if (!content) return null
  const parts = content.split(/(```[\s\S]*?```)/g)

  return (
    <div className="markdown-content">
      {parts.map((part, i) => {
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
          }} />
        ))
      })}
    </div>
  )
}

/* ── Send Icon (SVG matching agno-agi) ───────────────────────── */

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path d="M14 2L7 9M14 2L9.5 14L7 9M14 2L2 6.5L7 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}
