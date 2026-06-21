import { motion, AnimatePresence } from 'framer-motion'
import { useUIStore } from '@/stores/uiStore'
import { useActivityStore } from '@/stores/activityStore'
import { Bot, Brain, ListTodo, Activity, Mic, Cpu, X, AlertCircle, CheckCircle, Info } from 'lucide-react'

const typeIcons = {
  planner: Brain,
  agent: Bot,
  memory: Brain,
  queue: ListTodo,
  system: Activity,
  voice: Mic,
  model: Cpu,
}

const statusIcons = {
  info: Info,
  success: CheckCircle,
  warning: AlertCircle,
  error: AlertCircle,
}

const statusColors = {
  info: 'text-maya-blue',
  success: 'text-maya-green',
  warning: 'text-maya-orange',
  error: 'text-maya-red',
}

function formatTime(ts: number) {
  const diff = Math.floor((Date.now() - ts) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export function ActivityPanel() {
  const { activityPanelOpen, toggleActivityPanel } = useUIStore()
  const events = useActivityStore((s) => s.events)

  return (
    <AnimatePresence>
      {activityPanelOpen && (
        <motion.aside
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 280, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}
          className="h-full border-l border-maya-border bg-maya-bg-secondary/50 backdrop-blur-sm flex flex-col overflow-hidden"
        >
          <div className="flex items-center justify-between px-4 h-14 border-b border-maya-border flex-shrink-0">
            <span className="text-sm font-medium text-maya-text">Activity</span>
            <button onClick={toggleActivityPanel} className="text-maya-text-muted hover:text-maya-text transition-colors">
              <X size={14} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto py-2">
            {events.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-maya-text-muted">
                <Activity size={24} className="mb-2 opacity-40" />
                <span className="text-xs">No activity yet</span>
              </div>
            ) : (
              events.map((event) => {
                const TypeIcon = typeIcons[event.type]
                const StatusIcon = statusIcons[event.status]
                return (
                  <div
                    key={event.id}
                    className="px-4 py-2.5 hover:bg-white/5 transition-colors border-b border-maya-border/50 last:border-b-0"
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="mt-0.5 flex-shrink-0">
                        <TypeIcon size={14} className="text-maya-text-muted" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <StatusIcon size={12} className={statusColors[event.status]} />
                          <span className="text-xs font-medium text-maya-text truncate">{event.title}</span>
                        </div>
                        <p className="text-xs text-maya-text-secondary mt-0.5 truncate">{event.description}</p>
                        <span className="text-[10px] text-maya-text-muted mt-0.5 block">{formatTime(event.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
