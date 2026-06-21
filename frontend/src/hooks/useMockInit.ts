import { useEffect } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { useAgentStore } from '@/stores/agentStore'
import { useQueueStore } from '@/stores/queueStore'
import { useModelStore } from '@/stores/modelStore'
import { useMemoryStore } from '@/stores/memoryStore'
import { useActivityStore } from '@/stores/activityStore'
import {
  mockMessages, mockSessions, mockAgents, mockQueueTasks,
  mockPlan, mockModels, mockMemoryEntries, mockActivityEvents, mockLogs,
} from '@/services/mockData'

export function useMockInit() {
  useEffect(() => {
    useChatStore.getState().setMessages(mockMessages)
    useChatStore.getState().setSessions(mockSessions)
    useAgentStore.getState().setAgents(mockAgents)
    useQueueStore.getState().setTasks(mockQueueTasks)
    useQueueStore.getState().setPlan(mockPlan)
    useModelStore.getState().setModels(mockModels)
    useMemoryStore.getState().setEntries(mockMemoryEntries)
    useActivityStore.getState().setEvents(mockActivityEvents)
    useActivityStore.getState().setLogs(mockLogs)
    useActivityStore.getState().setHealth({
      brain: 'online',
      memory: 'online',
      agents: mockAgents.length,
      queueSize: mockQueueTasks.filter((t) => t.status === 'pending' || t.status === 'running').length,
      cloudStatus: 'connected',
      currentModel: 'claude-sonnet-4-20250514',
      latency: 245,
    })
  }, [])
}
