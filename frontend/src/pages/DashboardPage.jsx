import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bot, MessageSquare, Zap, Wrench, Code2, ArrowRight } from 'lucide-react'
import { agentsApi } from '../api/agents'
import { sessionsApi } from '../api/sessions'

export default function DashboardPage() {
  const navigate = useNavigate()

  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
    staleTime: 15_000,
  })

  const quickActions = [
    {
      title: 'Start chatting',
      desc: 'Talk to an agent about anything',
      icon: MessageSquare,
      action: () => navigate('/sessions'),
    },
    {
      title: 'Create an agent',
      desc: 'Configure a new AI agent',
      icon: Bot,
      action: () => navigate('/agents'),
    },
    {
      title: 'Train a model',
      desc: 'Fine-tune adapters on your data',
      icon: Zap,
      action: () => navigate('/training'),
    },
    {
      title: 'Open workspace',
      desc: 'Code editor, file browser, sandbox',
      icon: Code2,
      action: () => navigate('/workspace'),
    },
  ]

  return (
    <div style={{ flex: 1, overflow: 'auto' }}>
      <div className="chat-welcome">
        <div className="chat-welcome-icon">
          <Bot size={32} color="white" />
        </div>
        <h2>Welcome to Arena</h2>
        <p>
          Your autonomous AI agent platform. Chat with agents, manage tasks,
          train models, and execute tools — all in one place.
        </p>

        <div className="chat-welcome-suggestions">
          {quickActions.map((action) => {
            const Icon = action.icon
            return (
              <div
                key={action.title}
                className="chat-welcome-suggestion"
                onClick={action.action}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Icon size={16} style={{ color: 'var(--accent-blue)' }} />
                  <h4>{action.title}</h4>
                </div>
                <p>{action.desc}</p>
              </div>
            )
          })}
        </div>

        {agents && agents.length > 0 && (
          <div style={{ marginTop: 32, width: '100%', maxWidth: 500 }}>
            <h3 style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12, textAlign: 'left' }}>
              Your agents
            </h3>
            {agents.map((agent) => (
              <div
                key={agent.id}
                className="card"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '12px 16px',
                  marginBottom: 8,
                  cursor: 'pointer',
                }}
                onClick={() => navigate('/sessions')}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 'var(--radius-md)',
                    background: 'var(--accent-blue-dim)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Bot size={16} style={{ color: 'var(--accent-blue)' }} />
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{agent.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{agent.model}</div>
                  </div>
                </div>
                <div className={`badge status-${agent.status || 'idle'}`}>
                  <span className="badge-dot" />
                  {agent.status || 'idle'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
