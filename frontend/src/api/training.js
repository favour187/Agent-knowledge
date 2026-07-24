import { client } from './client'

export const trainingApi = {
  // Training runs
  listRuns: () => client.get('/training/runs').then((r) => r.data),
  getRun: (runId) => client.get(`/training/runs/${runId}`).then((r) => r.data),
  startTraining: (payload) => client.post('/training/start', payload).then((r) => r.data),
  dryRun: (payload) => client.post('/training/dry-run', payload).then((r) => r.data),

  // Datasets
  listDatasets: () => client.get('/training/datasets').then((r) => r.data),
  uploadDataset: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/training/datasets/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  // Adapters
  listAdapters: () => client.get('/training/adapters').then((r) => r.data),

  // Memory estimation
  estimateMemory: (payload) => client.post('/training/estimate-memory', payload).then((r) => r.data),
}
