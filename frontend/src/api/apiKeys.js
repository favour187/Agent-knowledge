import { client } from './client'

export const apiKeysApi = {
  list: () => client.get('/api-keys').then((r) => r.data),
  create: (payload) => client.post('/api-keys', payload).then((r) => r.data),
  remove: (id) => client.delete(`/api-keys/${id}`),
}
