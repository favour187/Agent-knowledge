import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from './components/ProtectedRoute'
import AppShell from './components/layout/AppShell'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import AgentsPage from './pages/AgentsPage'
import SessionsPage from './pages/SessionsPage'
import TasksPage from './pages/TasksPage'
import PlansPage from './pages/PlansPage'
import MemoryPage from './pages/MemoryPage'
import KnowledgePage from './pages/KnowledgePage'
import PatternsPage from './pages/PatternsPage'
import ToolsPage from './pages/ToolsPage'
import EvaluationPage from './pages/EvaluationPage'
import FeedbackPage from './pages/FeedbackPage'
import AuditPage from './pages/AuditPage'
import ApiKeysPage from './pages/ApiKeysPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="sessions" element={<SessionsPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="plans" element={<PlansPage />} />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="patterns" element={<PatternsPage />} />
        <Route path="tools" element={<ToolsPage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="feedback" element={<FeedbackPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="api-keys" element={<ApiKeysPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
