import { create } from 'zustand'

interface UIState {
  sidebarCollapsed: boolean
  activityPanelOpen: boolean
  currentPage: string
  mayaState: 'idle' | 'listening' | 'thinking' | 'planning' | 'executing' | 'speaking' | 'error'
  toggleSidebar: () => void
  toggleActivityPanel: () => void
  setCurrentPage: (page: string) => void
  setMayaState: (state: UIState['mayaState']) => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  activityPanelOpen: true,
  currentPage: 'chat',
  mayaState: 'idle',
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  toggleActivityPanel: () => set((s) => ({ activityPanelOpen: !s.activityPanelOpen })),
  setCurrentPage: (page) => set({ currentPage: page }),
  setMayaState: (mayaState) => set({ mayaState }),
}))
