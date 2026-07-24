import { client } from './client'

export const workspaceApi = {
  // File tree
  tree: (path = '') => client.get('/workspace/tree', { params: { path } }).then((r) => r.data),

  // File CRUD
  readFile: (path) => client.get('/workspace/file', { params: { path } }).then((r) => r.data),
  writeFile: (path, content) => client.post('/workspace/file', { path, content }).then((r) => r.data),
  createDir: (path) => client.post('/workspace/directory', { path }).then((r) => r.data),
  deleteFile: (path) => client.delete('/workspace/file', { params: { path } }).then((r) => r.data),

  // Code execution
  execute: (code, language = 'python', timeout = 30) =>
    client.post('/workspace/execute', { code, language, timeout }).then((r) => r.data),

  // Stats
  stats: () => client.get('/workspace/stats').then((r) => r.data),
}
