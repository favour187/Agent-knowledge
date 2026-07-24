import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Bot, MessagesSquare, ListChecks, Workflow,
  BrainCircuit, Network, Sparkles, Wrench, Gauge, ThumbsUp,
  ScrollText, KeyRound, Code2, Zap,
} from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { agentsApi } from '../../api/agents'
import { tasksApi } from '../../api/tasks'
import { plansApi } from '../../api/plans'

const primaryNav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/agents', label: 'Agents', icon: Bot, countQuery: ['agents', agentsApi.list] },
  { to: '/sessions', label: 'Sessions', icon: MessagesSquare },
  { to: '/tasks', label: 'Tasks', icon: ListChecks, countQuery: ['tasks', tasksApi.list] },
  { to: '/plans', label: 'Plans', icon: Workflow, countQuery: ['plans', plansApi.list] },
]

const intelligenceNav = [
  { to: '/memory', label: 'Memory', icon: BrainCircuit },
  { to: '/knowledge', label: 'Knowledge', icon: Network },
  { to: '/patterns', label: 'Patterns', icon: Sparkles },
  { to: '/tools', label: 'Tools', icon: Wrench },
  { to: '/workspace', label: 'Workspace', icon: Code2 },
  { to: '/training', label: 'Training', icon: Zap },
]

const qualityNav = [
  { to: '/evaluation', label: 'Evaluation', icon: Gauge },
  { to: '/feedback', label: 'Feedback', icon: ThumbsUp },
]

const systemNav = [
  { to: '/audit', label: 'Audit log', icon: ScrollText },
  { to: '/api-keys', label: 'API keys', icon: KeyRound },
]

function NavItem({ to, label, icon: Icon, end, countQuery }) {
  const { data } = useQuery({
    queryKey: countQuery || ['_noop'],
    queryFn: countQuery ? countQuery[1] : () => null,
    enabled: !!countQuery,
    staleTime: 30_000,
  })

  const count = countQuery && data ? data.length : null

  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
    >
      <span className="nav-link-left">
        <Icon size={15} />
        {label}
      </span>
      {count != null && count > 0 && (
        <span className="nav-link-count">{count}</span>
      )}
    </NavLink>
  )
}

function NavGroup({ items }) {
  return items.map((item) => <NavItem key={item.to} {...item} />)
}

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
      <div className="sidebar-inner">
        <div className="brand">
          <span className="brand-mark" />
          Arena
        </div>

        <NavGroup items={primaryNav} />

        <div className="nav-section-label">Intelligence</div>
        <NavGroup items={intelligenceNav} />

        <div className="nav-section-label">Quality</div>
        <NavGroup items={qualityNav} />

        <div className="nav-section-label">System</div>
        <NavGroup items={systemNav} />
      </div>

      {/* Sidebar footer: user info */}
      {user && (
        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-user-avatar">
              <UserInitials name={user.name} email={user.email} />
            </div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">{user.name || user.email}</div>
              {user.name && <div className="sidebar-user-email">{user.email}</div>}
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
