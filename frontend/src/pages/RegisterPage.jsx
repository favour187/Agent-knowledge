import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { authApi } from '../api/auth'
import { apiErrorMessage } from '../api/client'
import { useAuthStore } from '../store/authStore'
import { ErrorBanner } from '../components/ui/Primitives'

export default function RegisterPage() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)

  const mutation = useMutation({
    mutationFn: () => authApi.register({ name, email, password }),
    onSuccess: async () => {
      const { access_token } = await authApi.login({ email, password })
      const user = await authApi.me().catch(() => null)
      setSession(access_token, user)
      toast.success('Account created')
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
        <div className="brand" style={{ padding: '0 0 22px' }}>
          <span className="brand-mark pulse" />
          Arena
        </div>
        <h2 style={{ marginBottom: 4 }}>Create your account</h2>
        <p className="text-muted" style={{ fontSize: 13, marginBottom: 22 }}>
          Set up access to the platform.
        </p>

        <ErrorBanner message={mutation.isError ? apiErrorMessage(mutation.error) : null} />

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label htmlFor="name">Name</label>
            <input id="name" className="input" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={mutation.isPending}>
            {mutation.isPending ? 'Creating…' : 'Create account'}
          </button>
        </form>

        <p className="text-muted" style={{ fontSize: 13, marginTop: 18, textAlign: 'center' }}>
          Already have an account? <Link to="/login" style={{ color: 'var(--amber)' }}>Sign in</Link>
        </p>
      </div>
    </div>
  )
}
