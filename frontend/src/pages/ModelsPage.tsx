import { motion } from 'framer-motion'
import { useModelStore } from '@/stores/modelStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Brain, MessageSquare, Database, Zap, Gauge, TrendingUp, AlertTriangle, ArrowUpDown } from 'lucide-react'
import { ipcInvoke } from '@/services/ipc'

const roleIcons = {
  planner: Brain,
  response: MessageSquare,
  memory: Database,
  filler: Zap,
}

const roleColors = {
  planner: 'text-maya-purple border-maya-purple/20 bg-maya-purple/10',
  response: 'text-maya-cyan border-maya-cyan/20 bg-maya-cyan/10',
  memory: 'text-maya-blue border-maya-blue/20 bg-maya-blue/10',
  filler: 'text-maya-orange border-maya-orange/20 bg-maya-orange/10',
}

const roleDescriptions = {
  planner: 'Decomposes tasks into actionable plans and selects appropriate agents',
  response: 'Generates final responses to the user with full context',
  memory: 'Handles memory compression, retrieval, and context management',
  filler: 'Provides fast interim responses during processing delays',
}

export function ModelsPage() {
  const models = useModelStore((s) => s.models)

  const handleChangeModel = async (modelId: string) => {
    await ipcInvoke('change_model', { modelId })
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Model Management" subtitle="Configure AI models for each system role" />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {models.map((model, i) => {
          const Icon = roleIcons[model.role]
          const colorClass = roleColors[model.role]

          return (
            <motion.div
              key={model.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
            >
              <GlassPanel className="relative overflow-hidden">
                <div className="flex items-start gap-4 mb-4">
                  <div className={`w-12 h-12 rounded-xl border flex items-center justify-center flex-shrink-0 ${colorClass}`}>
                    <Icon size={24} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-semibold text-maya-text capitalize">{model.role} Model</h3>
                      <StatusBadge status={model.status} />
                    </div>
                    <p className="text-xs text-maya-text-secondary mt-1">{roleDescriptions[model.role]}</p>
                  </div>
                  <button
                    onClick={() => handleChangeModel(model.id)}
                    className="text-xs px-2.5 py-1.5 rounded-lg border border-maya-border bg-maya-surface hover:bg-maya-surface-hover text-maya-text-secondary hover:text-maya-text transition-all flex items-center gap-1.5"
                  >
                    <ArrowUpDown size={12} /> Switch
                  </button>
                </div>

                <div className="rounded-lg border border-maya-border bg-maya-bg/50 p-3 mb-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-mono text-maya-text">{model.model}</span>
                      <span className="text-xs text-maya-text-muted block mt-0.5">{model.provider}</span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-maya-border bg-maya-surface/30 p-2.5">
                    <div className="flex items-center gap-1.5 text-maya-text-muted mb-1">
                      <Gauge size={11} />
                      <span className="text-[10px]">Latency</span>
                    </div>
                    <span className="text-sm font-semibold text-maya-text">{model.latency}ms</span>
                  </div>
                  <div className="rounded-lg border border-maya-border bg-maya-surface/30 p-2.5">
                    <div className="flex items-center gap-1.5 text-maya-text-muted mb-1">
                      <TrendingUp size={11} />
                      <span className="text-[10px]">Success Rate</span>
                    </div>
                    <span className="text-sm font-semibold text-maya-green">{model.successRate}%</span>
                  </div>
                  <div className="rounded-lg border border-maya-border bg-maya-surface/30 p-2.5">
                    <div className="flex items-center gap-1.5 text-maya-text-muted mb-1">
                      <Zap size={11} />
                      <span className="text-[10px]">Tokens (In/Out)</span>
                    </div>
                    <span className="text-xs font-semibold text-maya-text">
                      {(model.tokenUsage.input / 1000).toFixed(1)}K / {(model.tokenUsage.output / 1000).toFixed(1)}K
                    </span>
                  </div>
                  <div className="rounded-lg border border-maya-border bg-maya-surface/30 p-2.5">
                    <div className="flex items-center gap-1.5 text-maya-text-muted mb-1">
                      <AlertTriangle size={11} />
                      <span className="text-[10px]">Fallbacks</span>
                    </div>
                    <span className={`text-sm font-semibold ${model.fallbackCount > 0 ? 'text-maya-orange' : 'text-maya-text'}`}>
                      {model.fallbackCount}
                    </span>
                  </div>
                </div>

                {model.lastError && (
                  <div className="mt-3 px-3 py-2 rounded-lg bg-maya-red/10 border border-maya-red/20">
                    <span className="text-xs text-maya-red">{model.lastError}</span>
                  </div>
                )}
              </GlassPanel>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
