import { client } from './client'

export const memoryApi = {
  search: (query, agentId) =>
    client.get('/memory', { params: { query, agent_id: agentId || undefined } }).then((r) => r.data),
  get: (id) => client.get(`/memory/${id}`).then((r) => r.data),
  create: (payload) => client.post('/memory', payload).then((r) => r.data),
  remove: (id) => client.delete(`/memory/${id}`),
  consolidate: () => client.post('/memory/consolidate').then((r) => r.data),
}
