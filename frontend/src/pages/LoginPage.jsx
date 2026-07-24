import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
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
      } catch {
        // /me failing shouldn't block login
      }
      toast.success('Signed in')
      navigate('/')
    },
  })

  function handleSubmit(e) {
    e.preventDefault()
    mutation.mutate()
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="brand" style={{ padding: '0 0 28px' }}>
          <span className="brand-mark" />
          Arena
        </div>
        <h2 style={{ marginBottom: 4, fontSize: 20 }}>Sign in</h2>
        <p className="text-muted" style={{ fontSize: 13, marginBottom: 24 }}>
          Control room for your agents, tasks, and memory.
        </p>

        <ErrorBanner message={mutation.isError ? apiErrorMessage(mutation.error) : null} />

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>
          <button
            className="btn btn-primary"
            style={{ width: '100%', justifyContent: 'center', marginTop: 4 }}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-muted" style={{ fontSize: 13, marginTop: 20, textAlign: 'center' }}>
          No account?{' '}
          <Link to="/register" style={{ color: 'var(--amber)', fontWeight: 500 }}>
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
