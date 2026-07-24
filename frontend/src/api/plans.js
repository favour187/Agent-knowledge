import { client } from './client'

export const plansApi = {
  list: () => client.get('/plans').then((r) => r.data),
  get: (id) => client.get(`/plans/${id}`).then((r) => r.data),
  create: (payload) => client.post('/plans', payload).then((r) => r.data),
  update: (id, payload) => client.put(`/plans/${id}`, payload).then((r) => r.data),
  remove: (id) => client.delete(`/plans/${id}`),
  addStep: (planId, payload) => client.post(`/plans/${planId}/steps`, payload).then((r) => r.data),
  updateStep: (stepId, payload) => client.put(`/plans/steps/${stepId}`, payload).then((r) => r.data),
}
