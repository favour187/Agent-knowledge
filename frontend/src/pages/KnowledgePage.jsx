import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, Link2, Network } from 'lucide-react'
import { knowledgeApi } from '../api/knowledge'
import { apiErrorMessage } from '../api/client'
import { SkeletonCards, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

export default function KnowledgePage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [relationOpen, setRelationOpen] = useState(false)

  const { data: entities, isLoading, error } = useQuery({ queryKey: ['knowledge', 'entities'], queryFn: knowledgeApi.listEntities })

  const removeMutation = useMutation({
    mutationFn: knowledgeApi.removeEntity,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'entities'] })
      toast.success('Entity deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h1 className="page-title">Knowledge base</h1>
          <p className="page-subtitle">Entities and relationships your agents reason over.</p>
        </div>
        <div className="flex-row">
          <button className="btn" onClick={() => setRelationOpen(true)}>
            <Link2 size={15} /> Add relation
          </button>
          <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> New entity
          </button>
        </div>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonCards count={6} />}

      {entities && entities.length === 0 && (
        <EmptyState
          title="No entities yet"
          hint="Add an entity to start building your knowledge graph."
          icon={Network}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> New entity
            </button>
          }
        />
      )}

      {entities && entities.length > 0 && (
        <div className="grid-cards">
          {entities.map((entity) => (
            <div key={entity.id} className="card">
              <div className="flex-row" style={{ justifyContent: 'space-between' }}>
                <span className="badge">{entity.entity_type}</span>
                <ConfirmButton onConfirm={() => removeMutation.mutate(entity.id)} />
              </div>
              <h3 style={{ fontSize: 15, marginTop: 10 }}>{entity.name}</h3>
              {entity.description && (
                <p className="text-muted" style={{ fontSize: 12.5, marginTop: 4 }}>
                  {entity.description}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {createOpen && <CreateEntityModal onClose={() => setCreateOpen(false)} />}
      {relationOpen && <CreateRelationModal entities={entities || []} onClose={() => setRelationOpen(false)} />}
    </div>
  )
}

function CreateEntityModal({ onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', entity_type: 'concept', description: '' })

  const mutation = useMutation({
    mutationFn: () => knowledgeApi.createEntity(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'entities'] })
      toast.success('Entity created')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New entity" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Name</label>
          <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="field">
          <label>Type</label>
          <input className="input" value={form.entity_type} onChange={(e) => setForm({ ...form, entity_type: e.target.value })} />
        </div>
        <div className="field">
          <label>Description</label>
          <textarea className="textarea" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create entity'}
        </button>
      </form>
    </Modal>
  )
}

function CreateRelationModal({ entities, onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ source_id: '', target_id: '', relation_type: '' })

  const mutation = useMutation({
    mutationFn: () => knowledgeApi.createRelation(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', 'entities'] })
      toast.success('Relation created')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New relation" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Source entity</label>
          <select className="select" required value={form.source_id} onChange={(e) => setForm({ ...form, source_id: e.target.value })}>
            <option value="" disabled>Choose entity</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>{e.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Relation type</label>
          <input
            className="input"
            required
            placeholder="e.g. depends_on"
            value={form.relation_type}
            onChange={(e) => setForm({ ...form, relation_type: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Target entity</label>
          <select className="select" required value={form.target_id} onChange={(e) => setForm({ ...form, target_id: e.target.value })}>
            <option value="" disabled>Choose entity</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>{e.name}</option>
            ))}
          </select>
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Linking…' : 'Create relation'}
        </button>
      </form>
    </Modal>
  )
}
