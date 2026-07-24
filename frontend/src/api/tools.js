import { client } from './client'

export const toolsApi = {
  list: () => client.get('/tools').then((r) => r.data),
  get: (name) => client.get(`/tools/${name}`).then((r) => r.data),
  executions: () => client.get('/tools/executions').then((r) => r.data),
  execute: (payload) => client.post('/tools/execute', payload).then((r) => r.data),
}
