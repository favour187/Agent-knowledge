import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Copy, KeyRound } from 'lucide-react'
import { apiKeysApi } from '../api/apiKeys'
import { apiErrorMessage } from '../api/client'
import { SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

export default function ApiKeysPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [freshKey, setFreshKey] = useState(null)

  const { data: keys, isLoading, error } = useQuery({ queryKey: ['api-keys'], queryFn: apiKeysApi.list })

  const removeMutation = useMutation({
    mutationFn: apiKeysApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      toast.success('Key revoked')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">API keys</h1>
          <p className="page-subtitle">Keys for programmatic access to the platform API.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New key
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && (
        <div className="card" style={{ padding: 0 }}>
          <SkeletonTable rows={3} cols={5} />
        </div>
      )}

      {keys && keys.length === 0 && (
        <EmptyState
          title="No API keys yet"
          hint="Create a key to authenticate programmatic requests."
          icon={KeyRound}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> New key
            </button>
          }
        />
      )}

      {keys && keys.length > 0 && (
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Key</th>
                <th>Rate limit</th>
                <th>Last used</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>{k.name}</td>
                  <td className="mono text-muted">{k.key_prefix}••••••••</td>
                  <td className="mono text-muted">{k.rate_limit}/hr</td>
                  <td className="text-muted">{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'never'}</td>
                  <td>
                    <ConfirmButton onConfirm={() => removeMutation.mutate(k.id)} children="Revoke" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <CreateKeyModal
          onClose={() => setCreateOpen(false)}
          onCreated={(key) => setFreshKey(key)}
        />
      )}
      {freshKey && <RevealKeyModal apiKey={freshKey} onClose={() => setFreshKey(null)} />}
    </div>
  )
}

function CreateKeyModal({ onClose, onCreated }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', rate_limit: 100 })

  const mutation = useMutation({
    mutationFn: () => apiKeysApi.create(form),
    onSuccess: (key) => {
      qc.invalidateQueries({ queryKey: ['api-keys'] })
      onCreated(key)
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New API key" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Name</label>
          <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="CI pipeline" />
        </div>
        <div className="field">
          <label>Rate limit (requests/hour)</label>
          <input
            className="input"
            type="number"
            min={1}
            value={form.rate_limit}
            onChange={(e) => setForm({ ...form, rate_limit: Number(e.target.value) })}
          />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create key'}
        </button>
      </form>
    </Modal>
  )
}

function RevealKeyModal({ apiKey, onClose }) {
  function copy() {
    navigator.clipboard.writeText(apiKey.api_key)
    toast.success('Copied to clipboard')
  }

  return (
    <Modal title="Save this key now" onClose={onClose}>
      <p className="text-muted" style={{ fontSize: 13, marginBottom: 14 }}>
        This is the only time the full key is shown. Store it somewhere safe.
      </p>
      <div
        className="card mono"
        style={{
          wordBreak: 'break-all',
          fontSize: 13,
          marginBottom: 14,
          background: 'var(--bg-canvas)',
          borderColor: 'var(--amber-dim)',
        }}
      >
        {apiKey.api_key}
      </div>
      <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={copy}>
        <Copy size={14} /> Copy key
      </button>
    </Modal>
  )
}
