import { useLocation, useNavigate } from 'react-router-dom'
import { Search, LogOut, Plus } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

const routeMeta = {
  '/': { title: 'Overview', subtitle: 'Arena AI Platform' },
  '/sessions': { title: 'Chat', subtitle: 'Conversation with agents' },
  '/agents': { title: 'Agents', subtitle: 'Manage your AI agents' },
  '/tasks': { title: 'Tasks', subtitle: 'Work queue' },
  '/plans': { title: 'Plans', subtitle: 'Goal decompositions' },
  '/memory': { title: 'Memory', subtitle: 'Agent memory store' },
  '/knowledge': { title: 'Knowledge', subtitle: 'Entity graph' },
  '/patterns': { title: 'Patterns', subtitle: 'Learned patterns' },
  '/tools': { title: 'Tools', subtitle: 'Tool registry' },
  '/workspace': { title: 'Workspace', subtitle: 'Sandbox & code editor' },
  '/training': { title: 'Training', subtitle: 'Fine-tune adapters' },
  '/evaluation': { title: 'Evaluation', subtitle: 'Self-evaluation' },
  '/feedback': { title: 'Feedback', subtitle: 'Human feedback' },
  '/audit': { title: 'Audit', subtitle: 'Action history' },
  '/api-keys': { title: 'API Keys', subtitle: 'Programmatic access' },
}

export default function Topbar({ onOpenCmd }) {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const location = useLocation()

  const meta = routeMeta[location.pathname] || { title: 'Arena', subtitle: '' }

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="topbar">
      <div className="topbar-left">
        <div>
          <div className="topbar-title">{meta.title}</div>
        </div>
      </div>

      <div className="topbar-right">
        <button className="topbar-search" onClick={onOpenCmd}>
          <Search size={14} />
          <span>Search or jump to…</span>
          <kbd>⌘K</kbd>
        </button>

        <button className="topbar-btn" onClick={handleLogout}>
          <LogOut size={14} />
        </button>
      </div>
    </div>
  )
}
