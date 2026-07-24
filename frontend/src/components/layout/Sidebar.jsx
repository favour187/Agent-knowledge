import { NavLink } from 'react-router-dom'
import {
  MessageSquare, LayoutDashboard, Bot, ListChecks, Workflow,
  BrainCircuit, Network, Sparkles, Wrench, Gauge, ThumbsUp,
  ScrollText, KeyRound, Code2, Zap, Settings,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview', end: true },
  { to: '/sessions', icon: MessageSquare, label: 'Chat' },
  { divider: true },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/tasks', icon: ListChecks, label: 'Tasks' },
  { to: '/plans', icon: Workflow, label: 'Plans' },
  { divider: true },
  { to: '/memory', icon: BrainCircuit, label: 'Memory' },
  { to: '/knowledge', icon: Network, label: 'Knowledge' },
  { to: '/patterns', icon: Sparkles, label: 'Patterns' },
  { to: '/tools', icon: Wrench, label: 'Tools' },
  { to: '/workspace', icon: Code2, label: 'Workspace' },
  { to: '/training', icon: Zap, label: 'Training' },
  { divider: true },
  { to: '/evaluation', icon: Gauge, label: 'Evaluation' },
  { to: '/feedback', icon: ThumbsUp, label: 'Feedback' },
  { to: '/audit', icon: ScrollText, label: 'Audit' },
  { to: '/api-keys', icon: KeyRound, label: 'API Keys' },
]

function UserInitials({ name, email }) {
  const display = name || email || '?'
  const parts = display.split(/[\s.@]+/).filter(Boolean)
  const initials = parts.length >= 2
    ? (parts[0][0] + parts[1][0]).toUpperCase()
    : display.slice(0, 2).toUpperCase()
  return <span>{initials}</span>
}

export default function Sidebar() {
  const user = useAuthStore((s) => s.user)

  return (
    <aside className="sidebar">
      <div className="sidebar-brand" title="Arena">
        A
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item, i) => {
          if (item.divider) {
            return <div key={`div-${i}`} className="sidebar-divider" />
          }

          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `sidebar-item${isActive ? ' active' : ''}`
              }
            >
              <Icon size={20} />
              <span className="sidebar-item-tooltip">{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="sidebar-bottom">
        <div className="sidebar-avatar" title={user?.email || 'User'}>
          <UserInitials name={user?.name} email={user?.email} />
        </div>
      </div>
    </aside>
  )
}
