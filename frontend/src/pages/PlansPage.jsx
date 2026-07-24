import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Plus, ChevronDown, ChevronRight, Workflow } from 'lucide-react'
import { plansApi } from '../api/plans'
import { apiErrorMessage } from '../api/client'
import { StatusBadge, SkeletonTable, EmptyState, ErrorBanner, Modal, ConfirmButton } from '../components/ui/Primitives'

export default function PlansPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const { data: plans, isLoading, error } = useQuery({ queryKey: ['plans'], queryFn: plansApi.list })

  const removeMutation = useMutation({
    mutationFn: plansApi.remove,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] })
      toast.success('Plan deleted')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1 className="page-title">Plans</h1>
          <p className="page-subtitle">Goal decompositions your agents execute step by step.</p>
        </div>
        <button className="btn btn-primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New plan
        </button>
      </div>

      <ErrorBanner message={error ? apiErrorMessage(error) : null} />
      {isLoading && <SkeletonTable rows={4} cols={3} />}

      {plans && plans.length === 0 && (
        <EmptyState
          title="No plans yet"
          hint="Create a plan to break a goal into steps."
          icon={Workflow}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => setCreateOpen(true)}>
              <Plus size={14} /> New plan
            </button>
          }
        />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {plans?.map((plan) => (
          <div key={plan.id} className="card">
            <div
              className="flex-row"
              style={{ justifyContent: 'space-between', cursor: 'pointer' }}
              onClick={() => setExpanded(expanded === plan.id ? null : plan.id)}
            >
              <div className="flex-row">
                {expanded === plan.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                <div>
                  <div style={{ fontWeight: 500 }}>{plan.goal}</div>
                  <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
                    {plan.steps.length} step{plan.steps.length === 1 ? '' : 's'} · {Math.round(plan.progress * 100)}% complete
                  </div>
                </div>
              </div>
              <div className="flex-row gap-sm" onClick={(e) => e.stopPropagation()}>
                <StatusBadge status={plan.status} />
                <ConfirmButton onConfirm={() => removeMutation.mutate(plan.id)} />
              </div>
            </div>

            {expanded === plan.id && (
              <div style={{ marginTop: 16, paddingLeft: 24, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {plan.steps.length === 0 && <p className="text-muted" style={{ fontSize: 13 }}>No steps yet.</p>}
                {plan.steps.map((step) => (
                  <PlanStepRow key={step.id} step={step} />
                ))}
                <AddStepForm planId={plan.id} />
              </div>
            )}
          </div>
        ))}
      </div>

      {createOpen && <CreatePlanModal onClose={() => setCreateOpen(false)} />}
    </div>
  )
}

function PlanStepRow({ step }) {
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: (status) => plansApi.updateStep(step.id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['plans'] }),
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <div
      className="flex-row"
      style={{ justifyContent: 'space-between', padding: '10px 12px', background: 'var(--bg-canvas)', borderRadius: 'var(--radius-md)' }}
    >
      <div>
        <div style={{ fontSize: 13.5 }}>{step.title}</div>
        {step.description && (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 2 }}>
            {step.description}
          </div>
        )}
      </div>
      <select
        className="select"
        style={{ width: 'auto', padding: '4px 8px', fontSize: 12 }}
        value={step.status}
        onChange={(e) => mutation.mutate(e.target.value)}
      >
        {['pending', 'running', 'completed', 'failed'].map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
    </div>
  )
}

function AddStepForm({ planId }) {
  const qc = useQueryClient()
  const [title, setTitle] = useState('')

  const mutation = useMutation({
    mutationFn: () => plansApi.addStep(planId, { title }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] })
      setTitle('')
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <form
      className="flex-row"
      onSubmit={(e) => {
        e.preventDefault()
        if (title.trim()) mutation.mutate()
      }}
    >
      <input className="input" placeholder="Add a step…" value={title} onChange={(e) => setTitle(e.target.value)} />
      <button className="btn btn-sm">Add</button>
    </form>
  )
}

function CreatePlanModal({ onClose }) {
  const qc = useQueryClient()
  const [goal, setGoal] = useState('')

  const mutation = useMutation({
    mutationFn: () => plansApi.create({ goal }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['plans'] })
      toast.success('Plan created')
      onClose()
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  })

  return (
    <Modal title="New plan" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate()
        }}
      >
        <div className="field">
          <label>Goal</label>
          <textarea className="textarea" rows={3} required value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="What should this plan accomplish?" />
        </div>
        <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
          {mutation.isPending ? 'Creating…' : 'Create plan'}
        </button>
      </form>
    </Modal>
  )
}
