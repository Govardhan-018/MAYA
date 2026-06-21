import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAgentStore } from '@/stores/agentStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import {
  Mail, Cloud, Calendar, Search, FolderOpen, Activity,
  Bot, Clock, TrendingUp, ChevronRight, X, Play, Zap,
} from 'lucide-react'

const iconMap: Record<string, typeof Bot> = {
  Mail, Cloud, Calendar, Search, FolderOpen, Activity,
}

export function AgentsPage() {
  const agents = useAgentStore((s) => s.agents)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = agents.find((a) => a.id === selectedId)

  return (
    <div className="h-full flex">
      <div className="flex-1 p-6 overflow-y-auto">
        <PageHeader title="Agents" subtitle={`${agents.length} registered agents`} />
        <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-4">
          {agents.map((agent, i) => {
            const Icon = iconMap[agent.icon || ''] || Bot
            return (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <GlassPanel hover className="cursor-pointer" onClick={() => setSelectedId(agent.id)}>
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-maya-cyan/10 border border-maya-cyan/20 flex items-center justify-center flex-shrink-0">
                      <Icon size={20} className="text-maya-cyan" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <h3 className="text-sm font-medium text-maya-text">{agent.name}</h3>
                        <StatusBadge status={agent.status} />
                      </div>
                      <p className="text-xs text-maya-text-secondary mt-1 line-clamp-1">{agent.description}</p>
                      <div className="flex items-center gap-4 mt-3 text-[11px] text-maya-text-muted">
                        <span className="flex items-center gap-1">
                          <TrendingUp size={10} /> {agent.successRate}%
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock size={10} /> {agent.avgDuration}s
                        </span>
                        <span className="flex items-center gap-1">
                          <Zap size={10} /> {agent.actions.length} actions
                        </span>
                      </div>
                    </div>
                    <ChevronRight size={14} className="text-maya-text-muted mt-2" />
                  </div>
                </GlassPanel>
              </motion.div>
            )
          })}
        </div>
      </div>

      <AnimatePresence>
        {selected && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 380, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-l border-maya-border bg-maya-bg-secondary/50 overflow-y-auto overflow-x-hidden"
          >
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-semibold text-maya-text">{selected.name}</h2>
                <button onClick={() => setSelectedId(null)} className="text-maya-text-muted hover:text-maya-text">
                  <X size={16} />
                </button>
              </div>

              <p className="text-sm text-maya-text-secondary mb-4">{selected.description}</p>
              <StatusBadge status={selected.status} size="md" />

              <div className="mt-6 grid grid-cols-2 gap-3">
                <GlassPanel>
                  <span className="text-[10px] text-maya-text-muted block">Success Rate</span>
                  <span className="text-lg font-semibold text-maya-green">{selected.successRate}%</span>
                </GlassPanel>
                <GlassPanel>
                  <span className="text-[10px] text-maya-text-muted block">Avg Duration</span>
                  <span className="text-lg font-semibold text-maya-cyan">{selected.avgDuration}s</span>
                </GlassPanel>
              </div>

              <h3 className="text-sm font-medium text-maya-text mt-6 mb-3">Actions</h3>
              <div className="space-y-2">
                {selected.actions.map((action) => (
                  <div key={action.name} className="rounded-lg border border-maya-border bg-maya-surface/50 p-3">
                    <div className="flex items-center gap-2">
                      <Play size={12} className="text-maya-cyan" />
                      <span className="text-xs font-mono text-maya-cyan">{action.name}</span>
                    </div>
                    <p className="text-xs text-maya-text-secondary mt-1">{action.description}</p>
                    {Object.keys(action.parameters).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {Object.entries(action.parameters).map(([key, type]) => (
                          <span key={key} className="text-[10px] px-1.5 py-0.5 rounded bg-maya-bg-tertiary text-maya-text-muted">
                            {key}: {type}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {selected.executionHistory.length > 0 && (
                <>
                  <h3 className="text-sm font-medium text-maya-text mt-6 mb-3">Recent Executions</h3>
                  <div className="space-y-2">
                    {selected.executionHistory.slice(0, 5).map((exec) => (
                      <div key={exec.id} className="flex items-center gap-2 text-xs">
                        <StatusBadge status={exec.status} />
                        <span className="text-maya-text-secondary font-mono">{exec.action}</span>
                        <span className="text-maya-text-muted ml-auto">{((exec.endTime - exec.startTime) / 1000).toFixed(1)}s</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
