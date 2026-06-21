import { create } from 'zustand'
import type { MemoryEntry } from '@/types'

interface MemoryState {
  entries: MemoryEntry[]
  searchQuery: string
  activeCategory: string | null
  setEntries: (entries: MemoryEntry[]) => void
  addEntry: (entry: MemoryEntry) => void
  setSearchQuery: (query: string) => void
  setActiveCategory: (category: string | null) => void
}

export const useMemoryStore = create<MemoryState>((set) => ({
  entries: [],
  searchQuery: '',
  activeCategory: null,
  setEntries: (entries) => set({ entries }),
  addEntry: (entry) => set((s) => ({ entries: [entry, ...s.entries] })),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setActiveCategory: (activeCategory) => set({ activeCategory }),
}))
