import { create } from 'zustand'
import type { Agent } from '@/types'

interface AgentState {
  agents: Agent[]
  selectedAgentId: string | null
  setAgents: (agents: Agent[]) => void
  updateAgent: (id: string, updates: Partial<Agent>) => void
  setSelectedAgent: (id: string | null) => void
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  selectedAgentId: null,
  setAgents: (agents) => set({ agents }),
  updateAgent: (id, updates) =>
    set((s) => ({
      agents: s.agents.map((a) => (a.id === id ? { ...a, ...updates } : a)),
    })),
  setSelectedAgent: (selectedAgentId) => set({ selectedAgentId }),
}))
