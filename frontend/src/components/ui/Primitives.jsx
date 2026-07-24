import { useState } from 'react'
import { X } from 'lucide-react'

export function StatusBadge({ status }) {
  const s = (status || 'unknown').toLowerCase()
  return (
    <span className={`badge status-${s}`}>
      <span className="badge-dot" />
      {s}
    </span>
  )
}

export function Spinner() {
  return <span className="spinner" />
}

export function LoadingBlock({ label = 'Loading…' }) {
  return (
    <div className="flex-row" style={{ padding: 32, color: 'var(--text-muted)' }}>
      <Spinner />
      <span>{label}</span>
    </div>
  )
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      {hint && <p>{hint}</p>}
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  )
}

export function ErrorBanner({ message }) {
  if (!message) return null
  return (
    <div
      className="card"
      style={{ borderColor: 'var(--danger-dim)', color: '#ff9a9d', marginBottom: 16, fontSize: 13 }}
    >
      {message}
    </div>
  )
}

export function Modal({ title, onClose, children, width }) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={width ? { maxWidth: width } : undefined}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

/** A destructive button that requires a second click within a few seconds to confirm. */
export function ConfirmButton({ onConfirm, children = 'Delete', className = 'btn btn-danger btn-sm' }) {
  const [armed, setArmed] = useState(false)

  function handleClick() {
    if (!armed) {
      setArmed(true)
      setTimeout(() => setArmed(false), 3000)
      return
    }
    setArmed(false)
    onConfirm()
  }

  return (
    <button className={className} onClick={handleClick}>
      {armed ? 'Confirm?' : children}
    </button>
  )
}
