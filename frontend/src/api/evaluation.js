import { client } from './client'

export const evaluationApi = {
  list: () => client.get('/evaluation').then((r) => r.data),
  get: (id) => client.get(`/evaluation/${id}`).then((r) => r.data),
  run: (payload) => client.post('/evaluation/run', payload).then((r) => r.data),
}
