import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { Plus, PanelLeftClose, PanelLeft, RefreshCw, LogOut } from 'lucide-react'

function UserInitials({ name, email }) {
  const display = name || email || '?'
  const parts = display.split(/[\s.@]+/).filter(Boolean)
  return parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : display.slice(0, 2).toUpperCase()
}

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  function handleNewChat() {
    window.dispatchEvent(new CustomEvent('arena-new-chat'))
  }

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        style={{
          position: 'absolute', right: 8, top: 12, zIndex: 10,
          background: 'transparent', border: 'none', color: 'var(--muted)',
          cursor: 'pointer', padding: 4,
        }}
      >
        {collapsed ? <PanelLeft size={16} /> : <PanelLeftClose size={16} />}
      </button>

      {!collapsed && (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          {/* Header */}
          <div className="sidebar-header">
            <div style={{
              width: 20, height: 20, borderRadius: 4,
              background: 'var(--brand)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ fontSize: 10, fontWeight: 700, color: 'white' }}>A</span>
            </div>
            <span className="sidebar-header-text">Arena</span>
          </div>

          {/* New Chat button */}
          <button className="sidebar-new-chat" onClick={handleNewChat} style={{ marginTop: 20 }}>
            <Plus size={14} />
            New Chat
          </button>

          {/* AgentOS section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">AgentOS</div>
            <div className="sidebar-status">
              <input
                className="sidebar-input"
                defaultValue="http://localhost:8000"
                readOnly
              />
              <div style={{ display: 'flex', gap: 4 }}>
                <div className="sidebar-status-dot active" title="Connected" />
              </div>
            </div>
          </div>

          {/* Auth token section */}
          <div className="sidebar-section">
            <div className="sidebar-section-label">Auth Token</div>
            <input
              className="sidebar-input"
              type="password"
              defaultValue="••••••••"
              readOnly
            />
          </div>

          {/* Sessions */}
          <div className="sidebar-sessions">
            <div className="sidebar-section-label" style={{ marginBottom: 8 }}>Sessions</div>
          </div>

          {/* User footer */}
          <div className="sidebar-user">
            <div className="sidebar-user-avatar">
              <UserInitials name={user?.name} email={user?.email} />
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <div style={{ fontSize: 12, color: 'var(--primary)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.name || user?.email}
              </div>
            </div>
            <button onClick={handleLogout} style={{
              background: 'transparent', border: 'none', color: 'var(--muted)',
              cursor: 'pointer', padding: 4,
            }}>
              <LogOut size={14} />
            </button>
          </div>
        </div>
      )}
    </aside>
  )
}
