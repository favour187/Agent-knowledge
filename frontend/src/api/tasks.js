import { client } from './client'

export const tasksApi = {
  list: () => client.get('/tasks').then((r) => r.data),
  get: (id) => client.get(`/tasks/${id}`).then((r) => r.data),
  create: (payload) => client.post('/tasks', payload).then((r) => r.data),
  update: (id, payload) => client.put(`/tasks/${id}`, payload).then((r) => r.data),
  remove: (id) => client.delete(`/tasks/${id}`),
}
