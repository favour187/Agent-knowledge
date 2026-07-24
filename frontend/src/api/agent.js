import { client } from './client'

export const agentApi = {
  // Autonomous chat — agent auto-executes tools
  chat: (message, sessionId) =>
    client.post('/agent/chat', { message, session_id: sessionId, execute_tools: true })
      .then((r) => r.data),

  // Model status
  status: () => client.get('/agent/status').then((r) => r.data),

  // Load model
  load: () => client.post('/agent/load').then((r) => r.data),
}
