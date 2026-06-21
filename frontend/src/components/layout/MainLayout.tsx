import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { ActivityPanel } from './ActivityPanel'
import { StatusBar } from './StatusBar'

export function MainLayout() {
  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-maya-bg">
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto overflow-x-hidden">
          <Outlet />
        </main>
        <ActivityPanel />
      </div>
      <StatusBar />
    </div>
  )
}
