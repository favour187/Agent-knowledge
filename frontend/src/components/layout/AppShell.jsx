import { useState, useEffect, useCallback } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import RightPanel from './RightPanel'
import { CommandPalette } from '../ui/Primitives'

export default function AppShell() {
  const [cmdOpen, setCmdOpen] = useState(false)
  const location = useLocation()
  const handleOpenCmd = useCallback(() => setCmdOpen(true), [])
  const handleCloseCmd = useCallback(() => setCmdOpen(false), [])

  useEffect(() => {
    function handleKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCmdOpen((open) => !open)
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [])

  // Show right panel only on chat page
  const showRightPanel = location.pathname === '/sessions'

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <Topbar onOpenCmd={handleOpenCmd} />
        <div className="chat-layout">
          <Outlet />
          {showRightPanel && <RightPanel />}
        </div>
      </div>
      <CommandPalette open={cmdOpen} onClose={handleCloseCmd} />
    </div>
  )
}
