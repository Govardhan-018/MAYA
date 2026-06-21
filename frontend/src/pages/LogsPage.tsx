import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { useActivityStore } from '@/stores/activityStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { Search, Filter } from 'lucide-react'

const levelColors = {
  debug: 'text-maya-text-muted',
  info: 'text-maya-blue',
  warn: 'text-maya-orange',
  error: 'text-maya-red',
}

const sourceColors = {
  brain: 'text-maya-purple',
  agent: 'text-maya-green',
  planner: 'text-maya-blue',
  memory: 'text-maya-cyan',
  voice: 'text-maya-orange',
  execution: 'text-maya-text-secondary',
}

export function LogsPage() {
  const logs = useActivityStore((s) => s.logs)
  const [search, setSearch] = useState('')
  const [sourceFilter, setSourceFilter] = useState<string | null>(null)
  const [levelFilter, setLevelFilter] = useState<string | null>(null)

  const filtered = useMemo(() => {
    let result = logs
    if (sourceFilter) result = result.filter((l) => l.source === sourceFilter)
    if (levelFilter) result = result.filter((l) => l.level === levelFilter)
    if (search) result = result.filter((l) => l.message.toLowerCase().includes(search.toLowerCase()))
    return result
  }, [logs, sourceFilter, levelFilter, search])

  const sources = ['brain', 'agent', 'planner', 'memory', 'voice', 'execution']
  const levels = ['debug', 'info', 'warn', 'error']

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Logs" subtitle={`${logs.length} entries`} />

      <div className="flex gap-3 mb-4">
        <div className="flex-1 flex items-center gap-2 rounded-lg border border-maya-border bg-maya-surface px-3">
          <Search size={14} className="text-maya-text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search logs..."
            className="bg-transparent text-sm text-maya-text placeholder:text-maya-text-muted outline-none py-2 flex-1"
          />
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-maya-border bg-maya-surface p-1">
          <button
            onClick={() => setSourceFilter(null)}
            className={`px-2 py-1.5 text-[10px] rounded-md ${!sourceFilter ? 'bg-maya-cyan/20 text-maya-cyan' : 'text-maya-text-muted'}`}
          >
            All
          </button>
          {sources.map((s) => (
            <button
              key={s}
              onClick={() => setSourceFilter(sourceFilter === s ? null : s)}
              className={`px-2 py-1.5 text-[10px] rounded-md capitalize ${
                sourceFilter === s ? 'bg-maya-cyan/20 text-maya-cyan' : 'text-maya-text-muted hover:text-maya-text'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-maya-border bg-maya-surface p-1">
          {levels.map((l) => (
            <button
              key={l}
              onClick={() => setLevelFilter(levelFilter === l ? null : l)}
              className={`px-2 py-1.5 text-[10px] rounded-md uppercase ${
                levelFilter === l ? 'bg-maya-cyan/20 text-maya-cyan' : `${levelColors[l as keyof typeof levelColors]} hover:opacity-80`
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      <GlassPanel padding={false} className="font-mono text-xs">
        <div className="divide-y divide-maya-border/50">
          {filtered.map((log, i) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.02 }}
              className="flex items-start gap-3 px-4 py-2 hover:bg-white/5"
            >
              <span className="text-maya-text-muted w-20 flex-shrink-0">
                {new Date(log.timestamp).toLocaleTimeString()}
              </span>
              <span className={`w-12 flex-shrink-0 uppercase font-semibold ${levelColors[log.level]}`}>
                {log.level}
              </span>
              <span className={`w-16 flex-shrink-0 capitalize ${sourceColors[log.source]}`}>
                {log.source}
              </span>
              <span className="text-maya-text flex-1">{log.message}</span>
            </motion.div>
          ))}
        </div>
      </GlassPanel>
    </div>
  )
}
