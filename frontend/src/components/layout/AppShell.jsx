import { useState, useEffect, useCallback } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Topbar from './Topbar'
import { CommandPalette } from '../ui/Primitives'

export default function AppShell() {
  const [cmdOpen, setCmdOpen] = useState(false)

  const handleOpenCmd = useCallback(() => setCmdOpen(true), [])
  const handleCloseCmd = useCallback(() => setCmdOpen(false), [])

  // Global ⌘K shortcut
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

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-col">
        <Topbar onOpenCmd={handleOpenCmd} />
        <Outlet />
      </div>
      <CommandPalette open={cmdOpen} onClose={handleCloseCmd} />
    </div>
  )
}
