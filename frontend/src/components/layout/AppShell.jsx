import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { Plus, Search, LogOut, Bot } from 'lucide-react'

export default function AppShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  function handleLogout() { logout(); navigate('/login') }
  function handleNewChat() { window.dispatchEvent(new CustomEvent('arena-new-chat')) }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-page)' }}>
      {/* Gradient header — exact from LMArenaBridge */}
      <div className="header">
        <div className="header-content">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{
                width: 32, height: 32, borderRadius: 8,
                background: 'rgba(255,255,255,0.2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Bot size={20} color="white" />
              </div>
              <h1>🚀 Arena AI Platform</h1>
            </div>
            <button className="header-btn" onClick={handleNewChat} style={{ marginLeft: 16 }}>
              <Plus size={14} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              New Chat
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {user && (
              <span style={{ fontSize: 13, opacity: 0.8 }}>{user.email}</span>
            )}
            <button className="header-btn" onClick={handleLogout}>Logout</button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <Outlet />
    </div>
  )
}
