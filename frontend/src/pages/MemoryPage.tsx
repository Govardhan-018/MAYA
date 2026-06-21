import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useMemoryStore } from '@/stores/memoryStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { Brain, Search, MessageSquare, Lightbulb, Heart, Bot, Database, Archive } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts'

const categoryConfig = {
  conversation: { icon: MessageSquare, color: 'text-maya-cyan', label: 'Conversations' },
  fact: { icon: Lightbulb, color: 'text-maya-orange', label: 'Facts' },
  preference: { icon: Heart, color: 'text-maya-purple', label: 'Preferences' },
  agent_history: { icon: Bot, color: 'text-maya-green', label: 'Agent History' },
  long_term: { icon: Database, color: 'text-maya-blue', label: 'Long Term' },
}

export function MemoryPage() {
  const entries = useMemoryStore((s) => s.entries)
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)

  const filtered = useMemo(() => {
    let result = entries
    if (activeCategory) result = result.filter((e) => e.category === activeCategory)
    if (search) result = result.filter((e) => e.content.toLowerCase().includes(search.toLowerCase()))
    return result
  }, [entries, activeCategory, search])

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const entry of entries) {
      counts[entry.category] = (counts[entry.category] || 0) + 1
    }
    return Object.entries(categoryConfig).map(([key, config]) => ({
      name: config.label,
      count: counts[key] || 0,
      key,
    }))
  }, [entries])

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Memory" subtitle={`${entries.length} memory entries`} />

      <div className="grid grid-cols-5 gap-3 mb-6">
        {categoryCounts.map(({ name, count, key }) => {
          const config = categoryConfig[key as keyof typeof categoryConfig]
          const Icon = config.icon
          const isActive = activeCategory === key
          return (
            <button key={key} onClick={() => setActiveCategory(isActive ? null : key)}>
              <GlassPanel className={`!p-3 text-left ${isActive ? 'border-maya-border-active' : ''}`}>
                <Icon size={14} className={config.color} />
                <span className="text-lg font-semibold text-maya-text block mt-1">{count}</span>
                <span className="text-[10px] text-maya-text-muted">{name}</span>
              </GlassPanel>
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-maya-border bg-maya-surface px-3 mb-4">
        <Search size={14} className="text-maya-text-muted" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search memory..."
          className="bg-transparent text-sm text-maya-text placeholder:text-maya-text-muted outline-none py-2 flex-1"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-6">
        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text mb-3 flex items-center gap-2">
            <Archive size={14} /> Memory Distribution
          </h3>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={categoryCounts}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip
                contentStyle={{ background: '#1a2332', border: '1px solid rgba(56, 189, 248, 0.15)', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Bar dataKey="count" fill="#22d3ee" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text mb-3 flex items-center gap-2">
            <Brain size={14} /> Vector Memory Stats
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <span className="text-[10px] text-maya-text-muted block">Total Vectors</span>
              <span className="text-sm font-semibold text-maya-text">{entries.length * 128}</span>
            </div>
            <div>
              <span className="text-[10px] text-maya-text-muted block">Dimensions</span>
              <span className="text-sm font-semibold text-maya-text">1536</span>
            </div>
            <div>
              <span className="text-[10px] text-maya-text-muted block">Index Size</span>
              <span className="text-sm font-semibold text-maya-text">{(entries.length * 0.8).toFixed(1)} MB</span>
            </div>
            <div>
              <span className="text-[10px] text-maya-text-muted block">Avg Retrieval</span>
              <span className="text-sm font-semibold text-maya-text">12ms</span>
            </div>
          </div>
        </GlassPanel>
      </div>

      <div className="space-y-2">
        {filtered.map((entry, i) => {
          const config = categoryConfig[entry.category]
          const Icon = config.icon
          return (
            <motion.div
              key={entry.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
            >
              <GlassPanel hover className="!py-3">
                <div className="flex items-start gap-3">
                  <Icon size={14} className={`${config.color} mt-0.5 flex-shrink-0`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-maya-text">{entry.content}</p>
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className={`text-[10px] ${config.color}`}>{config.label}</span>
                      <span className="text-[10px] text-maya-text-muted">
                        {new Date(entry.timestamp).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              </GlassPanel>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
