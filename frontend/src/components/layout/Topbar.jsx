import { useLocation, useNavigate } from 'react-router-dom'
import { LogOut, Search } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

const routeLabels = {
  '/': 'Overview',
  '/agents': 'Agents',
  '/sessions': 'Sessions',
  '/tasks': 'Tasks',
  '/plans': 'Plans',
  '/memory': 'Memory',
  '/knowledge': 'Knowledge',
  '/patterns': 'Patterns',
  '/tools': 'Tools',
  '/evaluation': 'Evaluation',
  '/feedback': 'Feedback',
  '/audit': 'Audit log',
  '/api-keys': 'API keys',
}

export default function Topbar({ onOpenCmd }) {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const location = useLocation()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  const currentLabel = routeLabels[location.pathname] || 'Arena'

  return (
    <div className="topbar">
      <div className="topbar-left">
        <div className="topbar-breadcrumb">
          <span style={{ color: 'var(--text-muted)' }}>arena</span>
          <span className="topbar-breadcrumb-sep">/</span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{currentLabel}</span>
        </div>
      </div>

      <div className="topbar-right">
        <button className="topbar-cmd-trigger" onClick={onOpenCmd}>
          <Search size={14} />
          <span>Search commands…</span>
          <span className="sidebar-kbd" style={{ marginLeft: 'auto' }}>⌘K</span>
        </button>

        <button className="btn btn-ghost btn-sm" onClick={handleLogout} title="Sign out">
          <LogOut size={14} />
        </button>
      </div>
    </div>
  )
}
