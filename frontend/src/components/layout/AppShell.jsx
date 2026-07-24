import { Outlet, useNavigate } from 'react-router-dom'
import { Plus, Search, LogOut, Bot } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

export default function AppShell() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  function handleLogout() {
    logout()
    navigate('/login')
  }

  function handleNewChat() {
    // Trigger new chat event
    window.dispatchEvent(new CustomEvent('arena-new-chat'))
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Nav — exactly like Arena */}
      <nav style={{
        height: 52,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        borderBottom: '1px solid var(--border-secondary)',
        background: 'var(--bg-secondary)',
        flexShrink: 0,
        zIndex: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }} onClick={handleNewChat}>
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Bot size={16} color="white" />
            </div>
            <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>Arena</span>
          </div>

          {/* Mode selector */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', borderRadius: 8,
            background: 'var(--accent-blue-dim)',
            color: 'var(--accent-blue)', fontSize: 13, fontWeight: 600,
          }}>
            Agent Mode
          </div>

          {/* New Chat */}
          <button onClick={handleNewChat} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 6,
            background: 'transparent', border: '1px solid var(--border-primary)',
            color: 'var(--text-secondary)', fontSize: 13, cursor: 'pointer',
          }}>
            <Plus size={14} /> New Chat
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 6,
            background: 'transparent', border: 'none',
            color: 'var(--text-muted)', fontSize: 12, cursor: 'pointer',
          }}>
            <Search size={14} /> Search
          </button>
          {user && (
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {user.email}
            </span>
          )}
          <button onClick={handleLogout} style={{
            display: 'flex', alignItems: 'center',
            padding: 6, borderRadius: 6,
            background: 'transparent', border: 'none',
            color: 'var(--text-muted)', cursor: 'pointer',
          }}>
            <LogOut size={16} />
          </button>
        </div>
      </nav>

      {/* Main content — the chat */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Outlet />
      </div>
    </div>
  )
}
