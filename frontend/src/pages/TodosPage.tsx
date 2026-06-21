import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { mockTodos } from '@/services/mockData'
import { CheckSquare, Square, Search, Tag, Filter, BarChart3 } from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'

const priorityColors = { low: 'text-maya-green', medium: 'text-maya-orange', high: 'text-maya-red' }

export function TodosPage() {
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'pending' | 'completed'>('all')
  const todos = mockTodos

  const filtered = useMemo(() => {
    let result = todos
    if (filter === 'pending') result = result.filter((t) => !t.completed)
    if (filter === 'completed') result = result.filter((t) => t.completed)
    if (search) result = result.filter((t) => t.title.toLowerCase().includes(search.toLowerCase()))
    return result
  }, [todos, filter, search])

  const completed = todos.filter((t) => t.completed).length
  const pending = todos.length - completed
  const pieData = [
    { name: 'Completed', value: completed },
    { name: 'Pending', value: pending },
  ]

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Todos" subtitle={`${pending} pending, ${completed} completed`} />

      <div className="flex gap-6 mb-6">
        <div className="flex-1 flex gap-3">
          <div className="flex-1 flex items-center gap-2 rounded-lg border border-maya-border bg-maya-surface px-3">
            <Search size={14} className="text-maya-text-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search todos..."
              className="bg-transparent text-sm text-maya-text placeholder:text-maya-text-muted outline-none py-2 flex-1"
            />
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-maya-border bg-maya-surface p-1">
            {(['all', 'pending', 'completed'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors capitalize ${
                  filter === f ? 'bg-maya-cyan/20 text-maya-cyan' : 'text-maya-text-muted hover:text-maya-text'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <GlassPanel className="!p-3 w-32">
          <div className="flex items-center gap-2">
            <ResponsiveContainer width={40} height={40}>
              <PieChart>
                <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={12} outerRadius={18} strokeWidth={0}>
                  <Cell fill="#10b981" />
                  <Cell fill="#64748b" />
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div>
              <span className="text-lg font-semibold text-maya-text">{Math.round((completed / todos.length) * 100)}%</span>
              <span className="text-[10px] text-maya-text-muted block">Done</span>
            </div>
          </div>
        </GlassPanel>
      </div>

      <div className="space-y-2">
        {filtered.map((todo, i) => (
          <motion.div
            key={todo.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03 }}
          >
            <GlassPanel hover className="!py-3">
              <div className="flex items-center gap-3">
                {todo.completed ? (
                  <CheckSquare size={16} className="text-maya-green flex-shrink-0" />
                ) : (
                  <Square size={16} className="text-maya-text-muted flex-shrink-0" />
                )}
                <span className={`text-sm flex-1 ${todo.completed ? 'text-maya-text-muted line-through' : 'text-maya-text'}`}>
                  {todo.title}
                </span>
                <span className={`text-[10px] font-medium capitalize ${priorityColors[todo.priority]}`}>
                  {todo.priority}
                </span>
                <div className="flex items-center gap-1">
                  {todo.tags.map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-maya-bg-tertiary text-maya-text-muted flex items-center gap-1">
                      <Tag size={8} /> {tag}
                    </span>
                  ))}
                </div>
              </div>
            </GlassPanel>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
