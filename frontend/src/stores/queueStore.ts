import { create } from 'zustand'
import type { QueueTask, Plan } from '@/types'

interface QueueState {
  tasks: QueueTask[]
  currentPlan: Plan | null
  setTasks: (tasks: QueueTask[]) => void
  addTask: (task: QueueTask) => void
  updateTask: (id: string, updates: Partial<QueueTask>) => void
  removeTask: (id: string) => void
  setPlan: (plan: Plan | null) => void
}

export const useQueueStore = create<QueueState>((set) => ({
  tasks: [],
  currentPlan: null,
  setTasks: (tasks) => set({ tasks }),
  addTask: (task) => set((s) => ({ tasks: [...s.tasks, task] })),
  updateTask: (id, updates) =>
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, ...updates } : t)),
    })),
  removeTask: (id) => set((s) => ({ tasks: s.tasks.filter((t) => t.id !== id) })),
  setPlan: (currentPlan) => set({ currentPlan }),
}))
