import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Play, Wrench } from 'lucide-react'
import { toolsApi } from '../api/tools'
import { apiErrorMessage } from '../api/client'
import { SkeletonCards, SkeletonTable, EmptyState, ErrorBanner, Modal } from '../components/ui/Primitives'

export default function ToolsPage() {
  const [runTool, setRunTool] = useState(null)
  const { data: tools, isLoading, error } = useQuery({ queryKey: ['tools'], queryFn: toolsApi.list })
  const { data: executions } = useQuery({ queryKey: ['tools', 'executions'], queryFn: toolsApi.executions })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Tools</h1>
          <p className="page-subtitle">The dynamic tool registry your agents can invoke, sandboxed on execution.</p>
        </div>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonCards count={4} />}

      {tools && tools.length === 0 && (
        <EmptyState title="No tools registered" hint="Register tools in the tool registry to make them available here." icon={Wrench} />
      )}

      {tools && tools.length > 0 && (
        <div className="grid-cards" style={{ marginBottom: 28 }}>
          {tools.map((tool) => (
            <div key={tool.name} className="card">
              <div className="flex-row" style={{ justifyContent: 'space-between' }}>
                <span className="badge">{tool.category}</span>
                {tool.requires_confirmation && <span className="badge status-pending">confirm</span>}
              </div>
              <h3 className="mono" style={{ fontSize: 14, marginTop: 10 }}>{tool.name}</h3>
              <p className="text-muted" style={{ fontSize: 12.5, marginTop: 4, marginBottom: 14 }}>{tool.description}</p>
              <button className="btn btn-sm" onClick={() => setRunTool(tool)}>
                <Play size={13} /> Run
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3 style={{ fontSize: 14, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Play size={14} style={{ color: 'var(--amber)' }} />
          Recent executions
        </h3>
        {isLoading && <SkeletonTable rows={3} cols={4} />}
        {(!executions || executions.length === 0) && !isLoading && (
          <p className="text-muted" style={{ fontSize: 13, padding: '8px 0' }}>No executions logged yet.</p>
        )}
        {executions && executions.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Tool</th>
                <th>Result</th>
                <th>Duration</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((ex) => (
                <tr key={ex.id}>
                  <td className="mono">{ex.tool_name}</td>
                  <td>
                    <span className={`badge ${ex.success ? 'status-success' : 'status-failed'}`}>
                      <span className="badge-dot" />
                      {ex.success ? 'success' : 'failed'}
                    </span>
                  </td>
                  <td className="mono text-muted">{ex.duration_ms != null ? `${ex.duration_ms}ms` : '—'}</td>
                  <td className="text-muted">{new Date(ex.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {runTool && <RunToolModal tool={runTool} onClose={() => setRunTool(null)} />}
    </div>
  )
}

function RunToolModal({ tool, onClose }) {
  const qc = useQueryClient()
  const [argsText, setArgsText] = useState('{}')
  const [result, setResult] = useState(null)

  const mutation = useMutation({
    mutationFn: () => {
      let args
      try {
        args = JSON.parse(argsText || '{}')
      } catch {
        throw new Error('Arguments must be valid JSON')
      }
      return toolsApi.execute({ tool_name: tool.name, arguments: args })
    },
    onSuccess: (res) => {
      setResult(res)
      qc.invalidateQueries({ queryKey: ['tools', 'executions'] })
      if (res.success) toast.success('Tool executed')
      else toast.error(res.error || 'Tool execution failed')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title={`Run ${tool.name}`} onClose={onClose} width={560}>
      <p className="text-muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
        Schema: <code className="mono">{JSON.stringify(tool.tool_schema)}</code>
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Arguments (JSON)</label>
          <textarea className="textarea" rows={5} value={argsText} onChange={(e) => setArgsText(e.target.value)} />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Running…' : 'Execute'}
        </button>
      </form>

      {result && (
        <div className="card" style={{ marginTop: 16, fontSize: 12.5 }}>
          <div className="text-muted" style={{ marginBottom: 8 }}>Result</div>
          <pre className="mono" style={{ whiteSpace: 'pre-wrap', margin: 0 }}>
            {JSON.stringify(result.output ?? result.error, null, 2)}
          </pre>
        </div>
      )}
    </Modal>
  )
}
