import { create } from 'zustand'
import type { ChatMessage, ChatSession } from '@/types'

interface ChatState {
  sessions: ChatSession[]
  activeSessionId: string | null
  messages: ChatMessage[]
  inputText: string
  setInputText: (text: string) => void
  addMessage: (message: ChatMessage) => void
  setMessages: (messages: ChatMessage[]) => void
  setSessions: (sessions: ChatSession[]) => void
  setActiveSession: (id: string) => void
  createSession: (session: ChatSession) => void
}

export const useChatStore = create<ChatState>((set) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  inputText: '',
  setInputText: (inputText) => set({ inputText }),
  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  setMessages: (messages) => set({ messages }),
  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (activeSessionId) => set({ activeSessionId }),
  createSession: (session) => set((s) => ({ sessions: [session, ...s.sessions], activeSessionId: session.id })),
}))
