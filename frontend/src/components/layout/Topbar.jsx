import { LogOut } from 'lucide-react'
import { useAuthStore } from '../../store/authStore'
import { useNavigate } from 'react-router-dom'

export default function Topbar() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="topbar">
      <div className="flex-row" style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
        <span className="mono">arena-ai-platform</span>
      </div>
      <div className="flex-row">
        {user && (
          <span className="mono" style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            {user.email}
          </span>
        )}
        <button className="btn btn-ghost btn-sm" onClick={handleLogout}>
          <LogOut size={14} />
          Sign out
        </button>
      </div>
    </div>
  )
}
