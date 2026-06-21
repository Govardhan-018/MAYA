import { useActivityStore } from '@/stores/activityStore'
import { useUIStore } from '@/stores/uiStore'
import { Brain, Database, Bot, ListTodo, Cloud, Cpu, Gauge, Heart, PanelRight } from 'lucide-react'

export function StatusBar() {
  const health = useActivityStore((s) => s.health)
  const mayaState = useUIStore((s) => s.mayaState)
  const { activityPanelOpen, toggleActivityPanel } = useUIStore()

  const stateColors: Record<string, string> = {
    idle: 'text-maya-text-muted',
    listening: 'text-maya-cyan',
    thinking: 'text-maya-purple',
    planning: 'text-maya-blue',
    executing: 'text-maya-orange',
    speaking: 'text-maya-green',
    error: 'text-maya-red',
  }

  return (
    <div className="h-7 bg-maya-bg-secondary/80 border-t border-maya-border flex items-center px-4 text-[11px] text-maya-text-muted gap-4 backdrop-blur-sm flex-shrink-0">
      <div className="flex items-center gap-1.5">
        <Heart size={11} className={stateColors[mayaState]} />
        <span className="capitalize">{mayaState}</span>
      </div>
      <div className="w-px h-3 bg-maya-border" />
      <div className="flex items-center gap-1.5">
        <Brain size={11} className={health.brain === 'online' ? 'text-maya-green' : 'text-maya-red'} />
        <span>Brain</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Database size={11} className={health.memory === 'online' ? 'text-maya-green' : 'text-maya-red'} />
        <span>Memory</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Bot size={11} />
        <span>{health.agents} Agents</span>
      </div>
      <div className="flex items-center gap-1.5">
        <ListTodo size={11} />
        <span>Queue: {health.queueSize}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Cloud size={11} className={health.cloudStatus === 'connected' ? 'text-maya-green' : 'text-maya-red'} />
        <span className="capitalize">{health.cloudStatus}</span>
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-1.5">
        <Cpu size={11} />
        <span>{health.currentModel}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <Gauge size={11} />
        <span>{health.latency}ms</span>
      </div>
      <div className="w-px h-3 bg-maya-border" />
      <button onClick={toggleActivityPanel} className={`hover:text-maya-text transition-colors ${activityPanelOpen ? 'text-maya-cyan' : ''}`}>
        <PanelRight size={12} />
      </button>
    </div>
  )
}
