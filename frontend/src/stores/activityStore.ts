import { create } from 'zustand'
import type { ActivityEvent, LogEntry, SystemHealth } from '@/types'

interface ActivityState {
  events: ActivityEvent[]
  logs: LogEntry[]
  health: SystemHealth
  addEvent: (event: ActivityEvent) => void
  setEvents: (events: ActivityEvent[]) => void
  addLog: (log: LogEntry) => void
  setLogs: (logs: LogEntry[]) => void
  setHealth: (health: Partial<SystemHealth>) => void
}

export const useActivityStore = create<ActivityState>((set) => ({
  events: [],
  logs: [],
  health: {
    brain: 'online',
    memory: 'online',
    agents: 0,
    queueSize: 0,
    cloudStatus: 'connected',
    currentModel: 'GPT-4',
    latency: 0,
  },
  addEvent: (event) => set((s) => ({ events: [event, ...s.events].slice(0, 100) })),
  setEvents: (events) => set({ events }),
  addLog: (log) => set((s) => ({ logs: [log, ...s.logs].slice(0, 500) })),
  setLogs: (logs) => set({ logs }),
  setHealth: (health) => set((s) => ({ health: { ...s.health, ...health } })),
}))
