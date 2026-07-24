import { client } from './client'

export const agentApi = {
  // Chat — autonomous agent with tool execution
  chat: (message, sessionId) =>
    client.post('/agent/chat', { message, session_id: sessionId, execute_tools: true })
      .then((r) => r.data),

  // Streaming chat — real-time token delivery
  chatStream: async function* (message, sessionId) {
    const response = await fetch('/api/agent/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId, execute_tools: true }),
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            yield data
          } catch {}
        }
      }
    }
  },

  // File upload
  upload: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/agent/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  // Sessions
  listSessions: () => client.get('/agent/sessions').then((r) => r.data),
  getSession: (id) => client.get(`/agent/sessions/${id}`).then((r) => r.data),
  deleteSession: (id) => client.delete(`/agent/sessions/${id}`).then((r) => r.data),

  // Model status
  status: () => client.get('/agent/status').then((r) => r.data),
  load: () => client.post('/agent/load').then((r) => r.data),
}
