import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { MainLayout } from '@/components/layout/MainLayout'
import { ChatPage } from '@/pages/ChatPage'
import { AgentsPage } from '@/pages/AgentsPage'
import { QueuePage } from '@/pages/QueuePage'
import { ModelsPage } from '@/pages/ModelsPage'
import { ProjectsPage } from '@/pages/ProjectsPage'
import { TodosPage } from '@/pages/TodosPage'
import { MemoryPage } from '@/pages/MemoryPage'
import { VoicePage } from '@/pages/VoicePage'
import { LogsPage } from '@/pages/LogsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { useMockInit } from '@/hooks/useMockInit'

function App() {
  useMockInit()

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/todos" element={<TodosPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/voice" element={<VoicePage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
