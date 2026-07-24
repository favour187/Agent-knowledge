import { useQuery } from '@tanstack/react-query'
import { auditApi } from '../api/audit'
import { apiErrorMessage } from '../api/client'
import { LoadingBlock, EmptyState, ErrorBanner } from '../components/ui/Primitives'

export default function AuditPage() {
  const { data: logs, isLoading, error } = useQuery({ queryKey: ['audit'], queryFn: auditApi.list })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Audit log</h1>
          <p className="page-subtitle">A record of actions taken across the platform.</p>
        </div>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <LoadingBlock />}

      {logs && logs.length === 0 && <EmptyState title="Nothing recorded yet" hint="Actions like logins and resource changes will show up here." />}

      {logs && logs.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Resource</th>
                <th>Resource ID</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="mono">{log.action}</td>
                  <td className="text-muted">{log.resource_type || '—'}</td>
                  <td className="mono text-muted" style={{ fontSize: 11.5 }}>{log.resource_id || '—'}</td>
                  <td className="text-muted">{new Date(log.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
