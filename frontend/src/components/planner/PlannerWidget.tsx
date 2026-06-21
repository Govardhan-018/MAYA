import { motion } from 'framer-motion'
import { useQueueStore } from '@/stores/queueStore'
import { CheckCircle, Circle, Loader, AlertCircle, ArrowDown } from 'lucide-react'
import { GlassPanel } from '@/components/common/GlassPanel'

const statusIcons = {
  pending: Circle,
  running: Loader,
  completed: CheckCircle,
  failed: AlertCircle,
}

const statusColors = {
  pending: 'text-maya-text-muted',
  running: 'text-maya-cyan',
  completed: 'text-maya-green',
  failed: 'text-maya-red',
}

export function PlannerWidget() {
  const plan = useQueueStore((s) => s.currentPlan)

  if (!plan) return null

  return (
    <GlassPanel className="mx-6 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-1.5 h-1.5 rounded-full bg-maya-purple animate-pulse" />
        <span className="text-xs font-medium text-maya-purple">Active Plan</span>
        <span className="text-xs text-maya-text-muted ml-auto capitalize">{plan.status}</span>
      </div>
      <p className="text-sm text-maya-text mb-3">{plan.goal}</p>

      <div className="space-y-1">
        {plan.steps.map((step, i) => {
          const Icon = statusIcons[step.status]
          return (
            <div key={step.id}>
              <motion.div
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className="flex items-start gap-2.5 py-1.5"
              >
                <Icon
                  size={14}
                  className={`mt-0.5 flex-shrink-0 ${statusColors[step.status]} ${step.status === 'running' ? 'animate-spin' : ''}`}
                />
                <div className="flex-1 min-w-0">
                  <span className="text-xs text-maya-text">{step.description}</span>
                  {step.agentName && (
                    <span className="text-[10px] text-maya-text-muted ml-2">[{step.agentName}]</span>
                  )}
                  {step.reasoning && step.status === 'running' && (
                    <p className="text-[10px] text-maya-text-muted mt-0.5 italic">{step.reasoning}</p>
                  )}
                </div>
              </motion.div>
              {i < plan.steps.length - 1 && (
                <div className="flex justify-start pl-[5px]">
                  <ArrowDown size={10} className="text-maya-border" />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </GlassPanel>
  )
}
