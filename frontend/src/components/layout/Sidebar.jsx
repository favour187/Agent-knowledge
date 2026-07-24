import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Bot,
  MessagesSquare,
  ListChecks,
  Workflow,
  BrainCircuit,
  Network,
  Sparkles,
  Wrench,
  Gauge,
  ThumbsUp,
  ScrollText,
  KeyRound,
} from 'lucide-react'

const primaryNav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/agents', label: 'Agents', icon: Bot },
  { to: '/sessions', label: 'Sessions', icon: MessagesSquare },
  { to: '/tasks', label: 'Tasks', icon: ListChecks },
  { to: '/plans', label: 'Plans', icon: Workflow },
]

const intelligenceNav = [
  { to: '/memory', label: 'Memory', icon: BrainCircuit },
  { to: '/knowledge', label: 'Knowledge', icon: Network },
  { to: '/patterns', label: 'Patterns', icon: Sparkles },
  { to: '/tools', label: 'Tools', icon: Wrench },
]

const qualityNav = [
  { to: '/evaluation', label: 'Evaluation', icon: Gauge },
  { to: '/feedback', label: 'Feedback', icon: ThumbsUp },
]

const systemNav = [
  { to: '/audit', label: 'Audit log', icon: ScrollText },
  { to: '/api-keys', label: 'API keys', icon: KeyRound },
]

function NavGroup({ items }) {
  return items.map(({ to, label, icon: Icon, end }) => (
    <NavLink
      key={to}
      to={to}
      end={end}
      className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
    >
      <span className="nav-link-left">
        <Icon size={15} />
        {label}
      </span>
    </NavLink>
  ))
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark pulse" />
        Arena
      </div>

      <NavGroup items={primaryNav} />

      <div className="nav-section-label">Intelligence</div>
      <NavGroup items={intelligenceNav} />

      <div className="nav-section-label">Quality</div>
      <NavGroup items={qualityNav} />

      <div className="nav-section-label">System</div>
      <NavGroup items={systemNav} />
    </aside>
  )
}
