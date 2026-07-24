import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Bot } from 'lucide-react'
import { authApi } from '../api/auth'
import { apiErrorMessage } from '../api/client'
import { useAuthStore } from '../store/authStore'
import { ErrorBanner } from '../components/ui/Primitives'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)

  const mutation = useMutation({
    mutationFn: () => authApi.login({ email, password }),
    onSuccess: async (data) => {
      setSession(data.access_token, null)
      try {
        const user = await authApi.me()
        setSession(data.access_token, user)
      } catch {}
      toast.success('Signed in')
      navigate('/')
    },
  })

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 32 }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12,
            background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Bot size={22} color="white" />
          </div>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700 }}>Arena</h1>
            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>AI Agent Platform</p>
          </div>
        </div>

        <ErrorBanner message={mutation.isError ? apiErrorMessage(mutation.error) : null} />

        <form onSubmit={(e) => { e.preventDefault(); mutation.mutate() }}>
          <div className="field">
            <label>Email</label>
            <input className="input" type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com" autoComplete="email" />
          </div>
          <div className="field">
            <label>Password</label>
            <input className="input" type="password" required value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••" autoComplete="current-password" />
          </div>
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
            disabled={mutation.isPending}>
            {mutation.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p style={{ fontSize: 13, marginTop: 20, textAlign: 'center', color: 'var(--text-muted)' }}>
          No account? <Link to="/register" style={{ color: 'var(--accent-blue)', fontWeight: 500 }}>Create one</Link>
        </p>
      </div>
    </div>
  )
}
