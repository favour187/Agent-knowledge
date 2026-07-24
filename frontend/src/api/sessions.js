import { client } from './client'

export const sessionsApi = {
  list: () => client.get('/sessions').then((r) => r.data),
  get: (id) => client.get(`/sessions/${id}`).then((r) => r.data),
  create: (payload) => client.post('/sessions', payload).then((r) => r.data),
  remove: (id) => client.delete(`/sessions/${id}`),
  messages: (id) => client.get(`/sessions/${id}/messages`).then((r) => r.data),
  sendMessage: (id, payload) => client.post(`/sessions/${id}/messages`, payload).then((r) => r.data),
}
