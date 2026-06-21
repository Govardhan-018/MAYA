import { ipcListen } from './ipc'
import { useUIStore } from '@/stores/uiStore'
import { useChatStore } from '@/stores/chatStore'
import { useAgentStore } from '@/stores/agentStore'
import { useQueueStore } from '@/stores/queueStore'
import { useVoiceStore } from '@/stores/voiceStore'
import { useModelStore } from '@/stores/modelStore'
import { useMemoryStore } from '@/stores/memoryStore'
import { useActivityStore } from '@/stores/activityStore'
import type { ChatMessage, Agent, QueueTask, Plan, MemoryEntry, ModelConfig, ActivityEvent, LogEntry, SystemHealth, VoiceState } from '@/types'

const cleanups: (() => void)[] = []

export async function initEventListeners() {
  cleanups.push(await ipcListen('maya:state_changed', (payload) => {
    useUIStore.getState().setMayaState((payload as { state: string }).state as 'idle' | 'listening' | 'thinking' | 'planning' | 'executing' | 'speaking' | 'error')
  }))

  cleanups.push(await ipcListen('maya:message', (payload) => {
    useChatStore.getState().addMessage(payload as ChatMessage)
  }))

  cleanups.push(await ipcListen('maya:agent_updated', (payload) => {
    const agent = payload as Agent
    useAgentStore.getState().updateAgent(agent.id, agent)
  }))

  cleanups.push(await ipcListen('maya:queue_updated', (payload) => {
    const task = payload as QueueTask
    useQueueStore.getState().updateTask(task.id, task)
  }))

  cleanups.push(await ipcListen('maya:plan_updated', (payload) => {
    useQueueStore.getState().setPlan(payload as Plan)
  }))

  cleanups.push(await ipcListen('maya:voice_state', (payload) => {
    useVoiceStore.getState().setVoiceState(payload as Partial<VoiceState>)
  }))

  cleanups.push(await ipcListen('maya:voice_waveform', (payload) => {
    useVoiceStore.getState().setWaveformData((payload as { data: number[] }).data)
  }))

  cleanups.push(await ipcListen('maya:model_updated', (payload) => {
    const model = payload as ModelConfig
    useModelStore.getState().updateModel(model.id, model)
  }))

  cleanups.push(await ipcListen('maya:memory_updated', (payload) => {
    useMemoryStore.getState().addEntry(payload as MemoryEntry)
  }))

  cleanups.push(await ipcListen('maya:activity', (payload) => {
    useActivityStore.getState().addEvent(payload as ActivityEvent)
  }))

  cleanups.push(await ipcListen('maya:log', (payload) => {
    useActivityStore.getState().addLog(payload as LogEntry)
  }))

  cleanups.push(await ipcListen('maya:health', (payload) => {
    useActivityStore.getState().setHealth(payload as Partial<SystemHealth>)
  }))
}

export function destroyEventListeners() {
  cleanups.forEach((fn) => fn())
  cleanups.length = 0
}
