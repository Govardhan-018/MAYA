import { create } from 'zustand'

interface SettingsState {
  theme: 'dark' | 'light'
  developerMode: boolean
  notifications: boolean
  performanceMode: boolean
  logLevel: 'debug' | 'info' | 'warn' | 'error'
  setSetting: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  theme: 'dark',
  developerMode: false,
  notifications: true,
  performanceMode: false,
  logLevel: 'info',
  setSetting: (key, value) => set({ [key]: value } as Partial<SettingsState>),
}))
