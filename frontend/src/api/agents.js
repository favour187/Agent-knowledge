import { client } from './client'

export const agentsApi = {
  list: () => client.get('/agents').then((r) => r.data),
  get: (id) => client.get(`/agents/${id}`).then((r) => r.data),
  create: (payload) => client.post('/agents', payload).then((r) => r.data),
  update: (id, payload) => client.put(`/agents/${id}`, payload).then((r) => r.data),
  remove: (id) => client.delete(`/agents/${id}`),
  start: (id) => client.post(`/agents/${id}/start`).then((r) => r.data),
  stop: (id) => client.post(`/agents/${id}/stop`).then((r) => r.data),
  message: (id, content) => client.post(`/agents/${id}/message`, { content }).then((r) => r.data),
}
