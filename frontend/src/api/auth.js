import { client } from './client'

export const authApi = {
  register: (payload) => client.post('/auth/register', payload).then((r) => r.data),
  login: (payload) => client.post('/auth/login', payload).then((r) => r.data),
  me: () => client.get('/auth/me').then((r) => r.data),
}
