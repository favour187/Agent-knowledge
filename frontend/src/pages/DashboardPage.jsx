import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { agentsApi } from '../api/agents'
import { tasksApi } from '../api/tasks'
import { plansApi } from '../api/plans'
import { auditApi } from '../api/audit'
import { LoadingBlock, EmptyState } from '../components/ui/Primitives'
import { formatDistanceToNow } from 'date-fns'

function useCount(key, fn) {
  return useQuery({ queryKey: [key], queryFn: fn, staleTime: 15_000 })
}

export default function DashboardPage() {
  const agents = useCount('agents', agentsApi.list)
  const tasks = useCount('tasks', tasksApi.list)
  const plans = useCount('plans', plansApi.list)
  const audit = useQuery({ queryKey: ['audit', 'recent'], queryFn: auditApi.list, staleTime: 15_000 })

  const activeAgents = (agents.data || []).filter((a) => a.status === 'running' || a.status === 'active').length
  const openTasks = (tasks.data || []).filter((t) => t.status !== 'completed' && t.status !== 'failed').length
  const activePlans = (plans.data || []).filter((p) => p.status !== 'completed').length

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-subtitle">Live state of your agents, tasks, and plans.</p>
        </div>
      </div>

      <div className="grid-cards" style={{ marginBottom: 26 }}>
        <StatCard label="Agents" value={agents.data?.length} sub={`${activeAgents} active`} to="/agents" />
        <StatCard label="Open tasks" value={openTasks} sub={`${tasks.data?.length ?? 0} total`} to="/tasks" />
        <StatCard label="Active plans" value={activePlans} sub={`${plans.data?.length ?? 0} total`} to="/plans" />
        <StatCard label="Audit events" value={audit.data?.length} sub="recorded" to="/audit" />
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 14, fontSize: 14 }}>Recent activity</h3>
        {audit.isLoading && <LoadingBlock />}
        {audit.data && audit.data.length === 0 && (
          <EmptyState title="No activity yet" hint="Actions across the platform will show up here." />
        )}
        {audit.data && audit.data.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Resource</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {audit.data.slice(0, 8).map((log) => (
                <tr key={log.id}>
                  <td className="mono">{log.action}</td>
                  <td className="text-muted">{log.resource_type || '—'}</td>
                  <td className="text-muted">{formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, to }) {
  return (
    <Link to={to} className="stat-card" style={{ textDecoration: 'none', display: 'block' }}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? '—'}</div>
      <div className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>
        {sub}
      </div>
    </Link>
  )
}
