import { client } from './client'

export const knowledgeApi = {
  listEntities: () => client.get('/knowledge/entity').then((r) => r.data),
  getEntity: (id) => client.get(`/knowledge/entity/${id}`).then((r) => r.data),
  createEntity: (payload) => client.post('/knowledge/entity', payload).then((r) => r.data),
  updateEntity: (id, payload) => client.put(`/knowledge/entity/${id}`, payload).then((r) => r.data),
  removeEntity: (id) => client.delete(`/knowledge/entity/${id}`),
  createRelation: (payload) => client.post('/knowledge/relation', payload).then((r) => r.data),
}
