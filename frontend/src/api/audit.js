import { client } from './client'

export const auditApi = {
  list: () => client.get('/audit').then((r) => r.data),
  get: (id) => client.get(`/audit/${id}`).then((r) => r.data),
}
