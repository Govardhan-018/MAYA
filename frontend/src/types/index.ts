export type MayaState = 'idle' | 'listening' | 'thinking' | 'planning' | 'executing' | 'speaking' | 'error'

export type MessageRole = 'user' | 'assistant' | 'system' | 'agent' | 'planner' | 'voice'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: number
  agentName?: string
  metadata?: Record<string, unknown>
}

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
  updatedAt: number
  archived: boolean
  summary?: string
}

export interface Agent {
  id: string
  name: string
  description: string
  status: 'idle' | 'running' | 'error' | 'disabled'
  lastExecution?: number
  successRate: number
  avgDuration: number
  actions: AgentAction[]
  executionHistory: AgentExecution[]
  icon?: string
}

export interface AgentAction {
  name: string
  description: string
  parameters: Record<string, string>
}

export interface AgentExecution {
  id: string
  agentId: string
  action: string
  status: 'success' | 'failed' | 'cancelled'
  startTime: number
  endTime: number
  result?: string
  error?: string
}

export type QueueTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface QueueTask {
  id: string
  name: string
  agentId: string
  agentName: string
  status: QueueTaskStatus
  priority: number
  createdAt: number
  startedAt?: number
  completedAt?: number
  dependencies: string[]
  progress?: number
  result?: string
  error?: string
}

export interface PlanStep {
  id: string
  description: string
  agentId?: string
  agentName?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  reasoning?: string
  order: number
  dependencies: string[]
}

export interface Plan {
  id: string
  goal: string
  steps: PlanStep[]
  status: 'planning' | 'executing' | 'completed' | 'failed'
  createdAt: number
}

export interface Project {
  id: string
  name: string
  description: string
  status: 'active' | 'paused' | 'completed' | 'archived'
  progress: number
  milestones: Milestone[]
  risks: Risk[]
  notes: string[]
  meetings: Meeting[]
  files: ProjectFile[]
  createdAt: number
  updatedAt: number
}

export interface Milestone {
  id: string
  name: string
  dueDate: number
  completed: boolean
}

export interface Risk {
  id: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  mitigated: boolean
}

export interface Meeting {
  id: string
  title: string
  date: number
  notes: string
}

export interface ProjectFile {
  id: string
  name: string
  path: string
  type: string
}

export interface TodoItem {
  id: string
  title: string
  completed: boolean
  tags: string[]
  priority: 'low' | 'medium' | 'high'
  createdAt: number
  completedAt?: number
}

export interface MemoryEntry {
  id: string
  content: string
  category: 'conversation' | 'fact' | 'preference' | 'agent_history' | 'long_term'
  timestamp: number
  metadata?: Record<string, unknown>
}

export interface ModelConfig {
  id: string
  role: 'planner' | 'response' | 'memory' | 'filler'
  name: string
  provider: string
  model: string
  latency: number
  successRate: number
  tokenUsage: { input: number; output: number }
  fallbackCount: number
  lastError?: string
  status: 'active' | 'error' | 'fallback'
}

export interface VoiceState {
  mode: 'push_to_talk' | 'wake_word' | 'continuous' | 'off'
  listening: boolean
  microphone: string
  conversationMode: boolean
  speechQueue: string[]
  fillerEnabled: boolean
  interruptEnabled: boolean
  waveformData: number[]
  micLevel: number
}

export interface ActivityEvent {
  id: string
  type: 'planner' | 'agent' | 'memory' | 'queue' | 'system' | 'voice' | 'model'
  title: string
  description: string
  timestamp: number
  status: 'info' | 'success' | 'warning' | 'error'
}

export interface LogEntry {
  id: string
  source: 'brain' | 'agent' | 'planner' | 'memory' | 'voice' | 'execution'
  level: 'debug' | 'info' | 'warn' | 'error'
  message: string
  timestamp: number
  metadata?: Record<string, unknown>
}

export interface SystemHealth {
  brain: 'online' | 'offline' | 'error'
  memory: 'online' | 'offline' | 'error'
  agents: number
  queueSize: number
  cloudStatus: 'connected' | 'disconnected'
  currentModel: string
  latency: number
}
