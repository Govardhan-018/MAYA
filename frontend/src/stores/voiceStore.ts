import { create } from 'zustand'
import type { VoiceState } from '@/types'

interface VoiceStoreState extends VoiceState {
  setVoiceState: (state: Partial<VoiceState>) => void
  setWaveformData: (data: number[]) => void
  setMicLevel: (level: number) => void
}

export const useVoiceStore = create<VoiceStoreState>((set) => ({
  mode: 'wake_word',
  listening: false,
  microphone: 'Default',
  conversationMode: false,
  speechQueue: [],
  fillerEnabled: true,
  interruptEnabled: true,
  waveformData: new Array(64).fill(0),
  micLevel: 0,
  setVoiceState: (state) => set((s) => ({ ...s, ...state })),
  setWaveformData: (waveformData) => set({ waveformData }),
  setMicLevel: (micLevel) => set({ micLevel }),
}))
