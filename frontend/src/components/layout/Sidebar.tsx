import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '@/stores/uiStore'
import {
  MessageSquare, FolderKanban, CheckSquare, Brain, Bot,
  ListTodo, Cpu, ScrollText, Settings, Mic, ChevronLeft, ChevronRight, Hexagon,
} from 'lucide-react'

const navItems = [
  { path: '/chat', icon: MessageSquare, label: 'Chat' },
  { path: '/projects', icon: FolderKanban, label: 'Projects' },
  { path: '/todos', icon: CheckSquare, label: 'Todos' },
  { path: '/memory', icon: Brain, label: 'Memory' },
  { path: '/agents', icon: Bot, label: 'Agents' },
  { path: '/queue', icon: ListTodo, label: 'Queue' },
  { path: '/models', icon: Cpu, label: 'Models' },
  { path: '/logs', icon: ScrollText, label: 'Logs' },
  { path: '/settings', icon: Settings, label: 'Settings' },
  { path: '/voice', icon: Mic, label: 'Voice' },
]

export function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { sidebarCollapsed, toggleSidebar } = useUIStore()

  return (
    <motion.aside
      className="h-full flex flex-col bg-maya-bg-secondary/50 border-r border-maya-border backdrop-blur-sm relative z-20"
      animate={{ width: sidebarCollapsed ? 64 : 200 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
    >
      <div className="flex items-center gap-2.5 px-4 h-14 border-b border-maya-border">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-maya-cyan to-maya-blue flex items-center justify-center flex-shrink-0">
          <Hexagon size={18} className="text-white" />
        </div>
        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.span
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              className="text-lg font-bold bg-gradient-to-r from-maya-cyan to-maya-blue bg-clip-text text-transparent whitespace-nowrap"
            >
              MAYA
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          const Icon = item.icon
          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`
                w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-all relative
                ${isActive
                  ? 'text-maya-cyan bg-maya-cyan/10'
                  : 'text-maya-text-secondary hover:text-maya-text hover:bg-white/5'
                }
              `}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-indicator"
                  className="absolute left-0 top-0 bottom-0 w-0.5 bg-maya-cyan"
                  transition={{ duration: 0.2 }}
                />
              )}
              <Icon size={18} className="flex-shrink-0" />
              <AnimatePresence>
                {!sidebarCollapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="whitespace-nowrap"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </button>
          )
        })}
      </nav>

      <button
        onClick={toggleSidebar}
        className="flex items-center justify-center h-10 border-t border-maya-border text-maya-text-muted hover:text-maya-text transition-colors"
      >
        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
    </motion.aside>
  )
}
