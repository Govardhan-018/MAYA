import { create } from 'zustand'
import type { ModelConfig } from '@/types'

interface ModelState {
  models: ModelConfig[]
  setModels: (models: ModelConfig[]) => void
  updateModel: (id: string, updates: Partial<ModelConfig>) => void
}

export const useModelStore = create<ModelState>((set) => ({
  models: [],
  setModels: (models) => set({ models }),
  updateModel: (id, updates) =>
    set((s) => ({
      models: s.models.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    })),
}))
