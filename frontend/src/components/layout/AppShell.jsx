import { Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { Plus, LogOut, Bot, PanelRightOpen } from 'lucide-react'

export default function AppShell() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  function handleLogout() { logout(); navigate('/login') }
  function handleNewChat() { window.dispatchEvent(new CustomEvent('arena-new-chat')) }
  function handleToggleWs() { window.dispatchEvent(new CustomEvent('arena-toggle-ws')) }

  return (
    <div className="app-shell">
      <nav className="topnav">
        <div className="topnav-left">
          <div className="topnav-logo">
            <Bot size={18} /> Arena
          </div>
          <div className="topnav-mode">Agent Mode ▾</div>
          <div className="topnav-links">
            <button className="topnav-link active" onClick={handleNewChat}>New Chat</button>
          </div>
        </div>
        <div className="topnav-right">
          <button className="topnav-ws-toggle" onClick={handleToggleWs}>
            <PanelRightOpen size={14} /> Workspace
          </button>
          {user && <span style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</span>}
          <button className="topnav-link" onClick={handleLogout}><LogOut size={14} /></button>
        </div>
      </nav>
      <div className="main-content">
        <Outlet />
      </div>
    </div>
  )
}
