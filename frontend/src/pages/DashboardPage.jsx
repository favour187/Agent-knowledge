import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { agentsApi } from '../api/agents'
import { tasksApi } from '../api/tasks'
import { plansApi } from '../api/plans'
import { auditApi } from '../api/audit'
import { SkeletonCards, SkeletonTable, EmptyState } from '../components/ui/Primitives'
import { formatDistanceToNow } from 'date-fns'
import { Bot, ListChecks, Workflow, ScrollText, Activity } from 'lucide-react'

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
  const isLoading = agents.isLoading || tasks.isLoading || plans.isLoading || audit.isLoading

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-subtitle">
            Live state of your agents, tasks, and plans across the platform.
          </p>
        </div>
      </div>

      {isLoading ? (
        <SkeletonCards count={4} />
      ) : (
        <div className="grid-cards" style={{ marginBottom: 28 }}>
          <StatCard
            label="Agents"
            value={agents.data?.length ?? 0}
            sub={`${activeAgents} active`}
            to="/agents"
            icon={Bot}
            color="amber"
          />
          <StatCard
            label="Open tasks"
            value={openTasks}
            sub={`${tasks.data?.length ?? 0} total`}
            to="/tasks"
            icon={ListChecks}
            color="teal"
          />
          <StatCard
            label="Active plans"
            value={activePlans}
            sub={`${plans.data?.length ?? 0} total`}
            to="/plans"
            icon={Workflow}
            color="violet"
          />
          <StatCard
            label="Audit events"
            value={audit.data?.length ?? 0}
            sub="recorded"
            to="/audit"
            icon={ScrollText}
            color="amber"
          />
        </div>
      )}

      <div className="card">
        <div className="flex-between" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Activity size={15} style={{ color: 'var(--amber)' }} />
            Recent activity
          </h3>
          {audit.data && audit.data.length > 0 && (
            <Link to="/audit" style={{ fontSize: 12, color: 'var(--amber)', textDecoration: 'none' }}>
              View all →
            </Link>
          )}
        </div>

        {audit.isLoading && <SkeletonTable rows={5} cols={3} />}

        {audit.data && audit.data.length === 0 && (
          <EmptyState
            title="No activity yet"
            hint="Actions across the platform will show up here."
            icon={Activity}
          />
        )}

        {audit.data && audit.data.length > 0 && (
          <div>
            {audit.data.slice(0, 8).map((log, i) => (
              <div
                key={log.id}
                className="activity-item"
                style={{ animationDelay: `${i * 0.04}s` }}
              >
                <div className="activity-dot" />
                <div className="activity-content">
                  <div className="activity-action">
                    <span className="mono" style={{ color: 'var(--amber)' }}>{log.action}</span>
                  </div>
                  <div className="activity-meta">
                    {log.resource_type || 'System'} · {formatDistanceToNow(new Date(log.created_at), { addSuffix: true })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

const colorMap = {
  amber: { bg: 'var(--amber-glow)', color: 'var(--amber)' },
  teal: { bg: 'var(--teal-glow)', color: 'var(--teal)' },
  violet: { bg: 'var(--violet-glow)', color: 'var(--violet)' },
}

function StatCard({ label, value, sub, to, icon: Icon, color = 'amber' }) {
  const c = colorMap[color] || colorMap.amber
  return (
    <Link to={to} className="stat-card">
      <div className="flex-between">
        <div className="stat-label">{label}</div>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 'var(--radius-md)',
            background: c.bg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: c.color,
          }}
        >
          <Icon size={16} />
        </div>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-trend stat-trend-neutral" style={{ marginTop: 8 }}>
        {sub}
      </div>
    </Link>
  )
}
