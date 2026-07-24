import { client } from './client'

export const feedbackApi = {
  list: () => client.get('/feedback').then((r) => r.data),
  get: (id) => client.get(`/feedback/${id}`).then((r) => r.data),
  create: (payload) => client.post('/feedback', payload).then((r) => r.data),
}
