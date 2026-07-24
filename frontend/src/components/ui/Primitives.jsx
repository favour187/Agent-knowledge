import { useState, useEffect, useCallback, useRef } from 'react'
import { X, Search, ArrowRight, CornerDownLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Bot, MessagesSquare, ListChecks, Workflow,
  BrainCircuit, Network, Sparkles, Wrench, Gauge, ThumbsUp,
  ScrollText, KeyRound, Code2,
} from 'lucide-react'

/* ---------- Status Badge ---------- */

export function StatusBadge({ status }) {
  const s = (status || 'unknown').toLowerCase()
  return (
    <span className={`badge status-${s}`}>
      <span className="badge-dot" />
      {s}
    </span>
  )
}

/* ---------- Spinner ---------- */

export function Spinner() {
  return <span className="spinner" />
}

/* ---------- Skeleton Loader ---------- */

export function Skeleton({ width, height, style, circle }) {
  return (
    <span
      className={`skeleton${circle ? ' skeleton-circle' : ''}`}
      style={{
        width: width || '100%',
        height: height || 14,
        display: 'inline-block',
        ...style,
      }}
    />
  )
}

export function SkeletonTable({ rows = 4, cols = 4 }) {
  return (
    <div style={{ padding: '4px 0' }}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} style={{ display: 'flex', gap: 16, padding: '12px 14px', borderBottom: '1px solid var(--border-soft)' }}>
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton
              key={c}
              width={c === 0 ? '35%' : c === cols - 1 ? '10%' : '20%'}
              height={13}
              style={{ opacity: 1 - r * 0.12 }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonCards({ count = 4 }) {
  return (
    <div className="grid-cards">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card" style={{ padding: 20 }}>
          <Skeleton width="40%" height={10} style={{ marginBottom: 10 }} />
          <Skeleton width="60%" height={26} style={{ marginBottom: 8 }} />
          <Skeleton width="50%" height={10} />
        </div>
      ))}
    </div>
  )
}

/* ---------- Loading Block ---------- */

export function LoadingBlock({ label = 'Loading…' }) {
  return (
    <div className="flex-row" style={{ padding: 36, color: 'var(--text-muted)', justifyContent: 'center' }}>
      <Spinner />
      <span style={{ fontSize: 13 }}>{label}</span>
    </div>
  )
}

/* ---------- Empty State ---------- */

export function EmptyState({ title, hint, action, icon: Icon }) {
  return (
    <div className="empty-state">
      {Icon && (
        <div className="empty-state-icon">
          <Icon size={22} />
        </div>
      )}
      <h3>{title}</h3>
      {hint && <p>{hint}</p>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}

/* ---------- Error Banner ---------- */

export function ErrorBanner({ message }) {
  if (!message) return null
  return (
    <div className="error-banner">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style={{ flexShrink: 0 }}>
        <path d="M8 1a7 7 0 100 14A7 7 0 008 1zM7 5a1 1 0 112 0v3a1 1 0 11-2 0V5zm1 7a1 1 0 100-2 1 1 0 000 2z" />
      </svg>
      {message}
    </div>
  )
}

/* ---------- Modal ---------- */

export function Modal({ title, onClose, children, width }) {
  useEffect(() => {
    const handleKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={width ? { maxWidth: width } : undefined}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

/* ---------- Confirm Button ---------- */

export function ConfirmButton({ onConfirm, children = 'Delete', className = 'btn btn-danger btn-sm' }) {
  const [armed, setArmed] = useState(false)
  const timerRef = useRef(null)

  function handleClick() {
    if (!armed) {
      setArmed(true)
      timerRef.current = setTimeout(() => setArmed(false), 3000)
      return
    }
    clearTimeout(timerRef.current)
    setArmed(false)
    onConfirm()
  }

  useEffect(() => () => clearTimeout(timerRef.current), [])

  return (
    <button className={className} onClick={handleClick}>
      {armed ? 'Confirm?' : children}
    </button>
  )
}

/* ---------- Command Palette ---------- */

const cmdPaletteRoutes = [
  { to: '/', label: 'Overview', hint: 'Dashboard', icon: LayoutDashboard, group: 'Navigation' },
  { to: '/agents', label: 'Agents', hint: 'Manage agents', icon: Bot, group: 'Navigation' },
  { to: '/sessions', label: 'Sessions', hint: 'Conversation threads', icon: MessagesSquare, group: 'Navigation' },
  { to: '/tasks', label: 'Tasks', hint: 'Work queue', icon: ListChecks, group: 'Navigation' },
  { to: '/plans', label: 'Plans', hint: 'Goal decompositions', icon: Workflow, group: 'Navigation' },
  { to: '/memory', label: 'Memory', hint: 'Agent memory store', icon: BrainCircuit, group: 'Intelligence' },
  { to: '/knowledge', label: 'Knowledge', hint: 'Entity graph', icon: Network, group: 'Intelligence' },
  { to: '/patterns', label: 'Patterns', hint: 'Learned patterns', icon: Sparkles, group: 'Intelligence' },
  { to: '/tools', label: 'Tools', hint: 'Tool registry', icon: Wrench, group: 'Intelligence' },
  { to: '/workspace', label: 'Workspace', hint: 'Sandbox & code editor', icon: Code2, group: 'Intelligence' },
  { to: '/evaluation', label: 'Evaluation', hint: 'Self-evaluation', icon: Gauge, group: 'Quality' },
  { to: '/feedback', label: 'Feedback', hint: 'Human feedback', icon: ThumbsUp, group: 'Quality' },
  { to: '/audit', label: 'Audit log', hint: 'Action history', icon: ScrollText, group: 'System' },
  { to: '/api-keys', label: 'API keys', hint: 'Programmatic access', icon: KeyRound, group: 'System' },
]

export function CommandPalette({ open, onClose }) {
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const navigate = useNavigate()
  const listRef = useRef(null)

  const filtered = cmdPaletteRoutes.filter((r) => {
    const q = query.toLowerCase()
    return (
      r.label.toLowerCase().includes(q) ||
      r.hint.toLowerCase().includes(q) ||
      r.group.toLowerCase().includes(q)
    )
  })

  // Group filtered results
  const groups = {}
  filtered.forEach((r) => {
    if (!groups[r.group]) groups[r.group] = []
    groups[r.group].push(r)
  })

  const flatList = filtered

  const handleSelect = useCallback((item) => {
    navigate(item.to)
    setQuery('')
    setActiveIdx(0)
    onClose()
  }, [navigate, onClose])

  useEffect(() => {
    if (!open) {
      setQuery('')
      setActiveIdx(0)
    }
  }, [open])

  useEffect(() => {
    setActiveIdx(0)
  }, [query])

  useEffect(() => {
    function handleKey(e) {
      if (!open) return
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setActiveIdx((i) => Math.min(i + 1, flatList.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setActiveIdx((i) => Math.max(i - 1, 0))
      }
      if (e.key === 'Enter' && flatList[activeIdx]) {
        e.preventDefault()
        handleSelect(flatList[activeIdx])
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, flatList, activeIdx, handleSelect, onClose])

  // Scroll active item into view
  useEffect(() => {
    if (!listRef.current) return
    const active = listRef.current.querySelector('.cmd-palette-item.active')
    if (active) active.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  if (!open) return null

  let idx = -1

  return (
    <div className="cmd-palette-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="cmd-palette">
        <div className="cmd-palette-input-wrap">
          <Search size={16} />
          <input
            className="cmd-palette-input"
            placeholder="Type a command or search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>
        <div className="cmd-palette-list" ref={listRef}>
          {Object.entries(groups).map(([group, items]) => (
            <div key={group}>
              <div className="cmd-palette-group-label">{group}</div>
              {items.map((item) => {
                idx++
                const Icon = item.icon
                const isActive = idx === activeIdx
                const currentIdx = idx
                return (
                  <div
                    key={item.to}
                    className={`cmd-palette-item${isActive ? ' active' : ''}`}
                    onClick={() => handleSelect(item)}
                    onMouseEnter={() => setActiveIdx(currentIdx)}
                  >
                    <div className="cmd-palette-item-icon">
                      <Icon size={15} />
                    </div>
                    <div className="cmd-palette-item-text">
                      <div className="cmd-palette-item-label">{item.label}</div>
                      <div className="cmd-palette-item-hint">{item.hint}</div>
                    </div>
                    {isActive && <ArrowRight size={14} style={{ color: 'var(--amber)' }} />}
                  </div>
                )
              })}
            </div>
          ))}
          {flatList.length === 0 && (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 }}>
              No results found
            </div>
          )}
        </div>
        <div className="cmd-palette-footer">
          <span><kbd>↑↓</kbd> Navigate</span>
          <span><kbd><CornerDownLeft size={10} /></kbd> Select</span>
          <span><kbd>Esc</kbd> Close</span>
        </div>
      </div>
    </div>
  )
}
