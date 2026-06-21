import { motion } from 'framer-motion'
import { useQueueStore } from '@/stores/queueStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Clock, ArrowRight, GitBranch, Layers } from 'lucide-react'
import type { QueueTaskStatus } from '@/types'

const statusOrder: QueueTaskStatus[] = ['running', 'pending', 'completed', 'failed', 'cancelled']

export function QueuePage() {
  const tasks = useQueueStore((s) => s.tasks)
  const plan = useQueueStore((s) => s.currentPlan)

  const grouped = statusOrder.reduce<Record<string, typeof tasks>>((acc, status) => {
    const filtered = tasks.filter((t) => t.status === status)
    if (filtered.length > 0) acc[status] = filtered
    return acc
  }, {})

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Work Queue" subtitle={`${tasks.length} tasks`} />

      {plan && (
        <GlassPanel className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <GitBranch size={14} className="text-maya-purple" />
            <span className="text-sm font-medium text-maya-text">Execution Plan</span>
            <span className="text-xs text-maya-text-muted ml-auto capitalize">{plan.status}</span>
          </div>
          <p className="text-xs text-maya-text-secondary mb-3">{plan.goal}</p>
          <div className="flex items-center gap-2 flex-wrap">
            {plan.steps.map((step, i) => (
              <div key={step.id} className="flex items-center gap-2">
                <div className={`
                  px-2.5 py-1 rounded-md text-xs border
                  ${step.status === 'completed' ? 'border-maya-green/30 bg-maya-green/10 text-maya-green' :
                    step.status === 'running' ? 'border-maya-cyan/30 bg-maya-cyan/10 text-maya-cyan' :
                    step.status === 'failed' ? 'border-maya-red/30 bg-maya-red/10 text-maya-red' :
                    'border-maya-border bg-maya-surface text-maya-text-muted'}
                `}>
                  {step.agentName || `Step ${step.order}`}
                </div>
                {i < plan.steps.length - 1 && <ArrowRight size={12} className="text-maya-text-muted" />}
              </div>
            ))}
          </div>
        </GlassPanel>
      )}

      <div className="space-y-6">
        {Object.entries(grouped).map(([status, statusTasks]) => (
          <div key={status}>
            <div className="flex items-center gap-2 mb-3">
              <Layers size={14} className="text-maya-text-muted" />
              <span className="text-sm font-medium text-maya-text capitalize">{status}</span>
              <span className="text-xs text-maya-text-muted">({statusTasks.length})</span>
            </div>
            <div className="space-y-2">
              {statusTasks.map((task, i) => (
                <motion.div
                  key={task.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <GlassPanel hover className="!py-3">
                    <div className="flex items-center gap-3">
                      <StatusBadge status={task.status} />
                      <div className="flex-1 min-w-0">
                        <span className="text-sm text-maya-text">{task.name}</span>
                        <span className="text-xs text-maya-text-muted ml-2">[{task.agentName}]</span>
                      </div>
                      {task.dependencies.length > 0 && (
                        <span className="text-[10px] text-maya-text-muted flex items-center gap-1">
                          <GitBranch size={10} /> {task.dependencies.length} deps
                        </span>
                      )}
                      {task.progress !== undefined && task.status === 'running' && (
                        <div className="w-20">
                          <div className="h-1.5 rounded-full bg-maya-bg-tertiary overflow-hidden">
                            <motion.div
                              className="h-full rounded-full bg-maya-cyan"
                              animate={{ width: `${task.progress}%` }}
                              transition={{ duration: 0.3 }}
                            />
                          </div>
                          <span className="text-[10px] text-maya-text-muted">{task.progress}%</span>
                        </div>
                      )}
                      {task.completedAt && task.startedAt && (
                        <span className="text-[10px] text-maya-text-muted flex items-center gap-1">
                          <Clock size={10} /> {((task.completedAt - task.startedAt) / 1000).toFixed(1)}s
                        </span>
                      )}
                    </div>
                  </GlassPanel>
                </motion.div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
