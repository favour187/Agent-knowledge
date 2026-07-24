import { client } from './client'

export const patternsApi = {
  list: () => client.get('/patterns').then((r) => r.data),
  get: (id) => client.get(`/patterns/${id}`).then((r) => r.data),
  create: (payload) => client.post('/patterns', payload).then((r) => r.data),
  remove: (id) => client.delete(`/patterns/${id}`),
}
