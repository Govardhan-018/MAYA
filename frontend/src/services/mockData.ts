import type {
  ChatMessage, ChatSession, Agent, QueueTask, Plan, Project,
  TodoItem, MemoryEntry, ModelConfig, ActivityEvent, LogEntry
} from '@/types'

const now = Date.now()
const h = (hours: number) => now - hours * 3600000
const m = (mins: number) => now - mins * 60000

export const mockMessages: ChatMessage[] = [
  { id: '1', role: 'user', content: 'Hey MAYA, check my emails and give me a summary.', timestamp: m(5) },
  { id: '2', role: 'planner', content: 'Planning: 1) Access Gmail via agent 2) Fetch unread emails 3) Summarize content 4) Present results', timestamp: m(4) },
  { id: '3', role: 'agent', content: 'Gmail Agent: Found 12 unread emails. Fetching content...', timestamp: m(3), agentName: 'Gmail' },
  { id: '4', role: 'assistant', content: 'Here\'s your email summary:\n\n**Priority:**\n- Meeting rescheduled to 3 PM tomorrow (from Sarah)\n- Deploy approval needed for v2.1 (from DevOps)\n\n**Updates:**\n- 3 newsletter digests\n- 2 GitHub notifications\n- Sprint retrospective notes shared\n\n**Low Priority:**\n- 4 marketing emails', timestamp: m(2) },
  { id: '5', role: 'system', content: 'Memory updated: Email check pattern recorded.', timestamp: m(1) },
]

export const mockSessions: ChatSession[] = [
  { id: 's1', title: 'Email Summary & Tasks', messages: mockMessages, createdAt: h(1), updatedAt: m(1), archived: false },
  { id: 's2', title: 'Project Brainstorm', messages: [], createdAt: h(24), updatedAt: h(23), archived: false, summary: 'Discussed new feature ideas for Q3' },
  { id: 's3', title: 'Code Review Help', messages: [], createdAt: h(48), updatedAt: h(47), archived: true, summary: 'Reviewed authentication module changes' },
]

export const mockAgents: Agent[] = [
  {
    id: 'gmail', name: 'Gmail Agent', description: 'Manages email operations via Gmail API',
    status: 'idle', lastExecution: m(3), successRate: 97.5, avgDuration: 2.3,
    actions: [
      { name: 'read_emails', description: 'Read unread emails', parameters: { max_results: 'number', label: 'string' } },
      { name: 'send_email', description: 'Send an email', parameters: { to: 'string', subject: 'string', body: 'string' } },
      { name: 'search_emails', description: 'Search emails', parameters: { query: 'string' } },
    ],
    executionHistory: [
      { id: 'e1', agentId: 'gmail', action: 'read_emails', status: 'success', startTime: m(3), endTime: m(2), result: '12 emails fetched' },
    ],
    icon: 'Mail',
  },
  {
    id: 'weather', name: 'Weather Agent', description: 'Fetches weather data and forecasts',
    status: 'idle', lastExecution: m(30), successRate: 99.1, avgDuration: 0.8,
    actions: [
      { name: 'get_weather', description: 'Get current weather', parameters: { location: 'string' } },
      { name: 'get_forecast', description: 'Get weather forecast', parameters: { location: 'string', days: 'number' } },
    ],
    executionHistory: [],
    icon: 'Cloud',
  },
  {
    id: 'calendar', name: 'Calendar Agent', description: 'Google Calendar management',
    status: 'idle', lastExecution: h(2), successRate: 95.2, avgDuration: 1.5,
    actions: [
      { name: 'get_events', description: 'List upcoming events', parameters: { days: 'number' } },
      { name: 'create_event', description: 'Create calendar event', parameters: { title: 'string', datetime: 'string' } },
    ],
    executionHistory: [],
    icon: 'Calendar',
  },
  {
    id: 'web_search', name: 'Web Search Agent', description: 'Search the web for information',
    status: 'idle', lastExecution: h(1), successRate: 98.0, avgDuration: 3.1,
    actions: [
      { name: 'search', description: 'Search the web', parameters: { query: 'string' } },
      { name: 'summarize_url', description: 'Summarize a webpage', parameters: { url: 'string' } },
    ],
    executionHistory: [],
    icon: 'Search',
  },
  {
    id: 'file_manager', name: 'File Manager', description: 'Local file system operations',
    status: 'idle', successRate: 100, avgDuration: 0.3,
    actions: [
      { name: 'read_file', description: 'Read file contents', parameters: { path: 'string' } },
      { name: 'write_file', description: 'Write to file', parameters: { path: 'string', content: 'string' } },
    ],
    executionHistory: [],
    icon: 'FolderOpen',
  },
  {
    id: 'system_monitor', name: 'System Monitor', description: 'Monitor system resources and health',
    status: 'running', successRate: 99.8, avgDuration: 0.1,
    actions: [
      { name: 'get_stats', description: 'Get system statistics', parameters: {} },
    ],
    executionHistory: [],
    icon: 'Activity',
  },
]

export const mockQueueTasks: QueueTask[] = [
  { id: 'q1', name: 'Fetch Emails', agentId: 'gmail', agentName: 'Gmail', status: 'completed', priority: 1, createdAt: m(5), startedAt: m(4), completedAt: m(3), dependencies: [], progress: 100 },
  { id: 'q2', name: 'Check Weather', agentId: 'weather', agentName: 'Weather', status: 'completed', priority: 2, createdAt: m(5), startedAt: m(3), completedAt: m(2), dependencies: [], progress: 100 },
  { id: 'q3', name: 'Summarize Content', agentId: 'web_search', agentName: 'Web Search', status: 'running', priority: 3, createdAt: m(5), startedAt: m(1), dependencies: ['q1'], progress: 65 },
  { id: 'q4', name: 'Update Calendar', agentId: 'calendar', agentName: 'Calendar', status: 'pending', priority: 4, createdAt: m(5), dependencies: ['q3'] },
  { id: 'q5', name: 'Generate Report', agentId: 'file_manager', agentName: 'File Manager', status: 'pending', priority: 5, createdAt: m(5), dependencies: ['q3', 'q4'] },
]

export const mockPlan: Plan = {
  id: 'p1',
  goal: 'Check emails and prepare daily summary',
  status: 'executing',
  createdAt: m(5),
  steps: [
    { id: 'ps1', description: 'Fetch unread emails from Gmail', agentId: 'gmail', agentName: 'Gmail', status: 'completed', order: 1, dependencies: [], reasoning: 'Need to access email data first' },
    { id: 'ps2', description: 'Check weather for daily briefing', agentId: 'weather', agentName: 'Weather', status: 'completed', order: 2, dependencies: [], reasoning: 'Weather runs in parallel with email' },
    { id: 'ps3', description: 'Summarize email content using LLM', agentName: 'Brain', status: 'running', order: 3, dependencies: ['ps1'], reasoning: 'Requires email data to summarize' },
    { id: 'ps4', description: 'Update calendar with action items', agentId: 'calendar', agentName: 'Calendar', status: 'pending', order: 4, dependencies: ['ps3'], reasoning: 'Depends on summary to identify action items' },
  ],
}

export const mockProjects: Project[] = [
  {
    id: 'proj1', name: 'MAYA v2.0', description: 'Next generation AI assistant with full agent ecosystem',
    status: 'active', progress: 68,
    milestones: [
      { id: 'm1', name: 'Core Brain Engine', dueDate: h(24 * 30), completed: true },
      { id: 'm2', name: 'Agent Framework', dueDate: h(24 * 15), completed: true },
      { id: 'm3', name: 'Voice System', dueDate: h(24 * 5), completed: false },
      { id: 'm4', name: 'Frontend Dashboard', dueDate: now + 86400000 * 10, completed: false },
    ],
    risks: [
      { id: 'r1', description: 'Voice latency might exceed 500ms target', severity: 'medium', mitigated: false },
      { id: 'r2', description: 'API rate limits on Gmail', severity: 'low', mitigated: true },
    ],
    notes: ['Focus on voice response time optimization', 'Consider Whisper API fallback'],
    meetings: [{ id: 'mt1', title: 'Sprint Review', date: now + 86400000 * 2, notes: 'Review voice system progress' }],
    files: [{ id: 'f1', name: 'architecture.md', path: '/docs/architecture.md', type: 'markdown' }],
    createdAt: h(24 * 60), updatedAt: h(2),
  },
]

export const mockTodos: TodoItem[] = [
  { id: 't1', title: 'Implement voice interrupt handling', completed: false, tags: ['voice', 'priority'], priority: 'high', createdAt: h(5) },
  { id: 't2', title: 'Add agent retry logic', completed: false, tags: ['agents', 'reliability'], priority: 'medium', createdAt: h(10) },
  { id: 't3', title: 'Write memory compression algorithm', completed: false, tags: ['memory', 'optimization'], priority: 'high', createdAt: h(24) },
  { id: 't4', title: 'Set up model fallback chain', completed: true, tags: ['models'], priority: 'high', createdAt: h(48), completedAt: h(6) },
  { id: 't5', title: 'Create agent performance dashboard', completed: true, tags: ['frontend', 'agents'], priority: 'medium', createdAt: h(72), completedAt: h(12) },
  { id: 't6', title: 'Test wake word detection accuracy', completed: false, tags: ['voice', 'testing'], priority: 'low', createdAt: h(3) },
]

export const mockMemoryEntries: MemoryEntry[] = [
  { id: 'mem1', content: 'User prefers concise email summaries grouped by priority', category: 'preference', timestamp: m(2) },
  { id: 'mem2', content: 'Gmail Agent fetched 12 unread emails successfully', category: 'agent_history', timestamp: m(3) },
  { id: 'mem3', content: 'User has a meeting tomorrow at 3 PM with Sarah', category: 'fact', timestamp: m(4) },
  { id: 'mem4', content: 'Previous conversation about project architecture decisions', category: 'conversation', timestamp: h(24) },
  { id: 'mem5', content: 'User works in software engineering, prefers technical detail', category: 'long_term', timestamp: h(168) },
]

export const mockModels: ModelConfig[] = [
  { id: 'planner', role: 'planner', name: 'Planner Model', provider: 'OpenAI', model: 'gpt-4o', latency: 320, successRate: 99.2, tokenUsage: { input: 45200, output: 12800 }, fallbackCount: 1, status: 'active' },
  { id: 'response', role: 'response', name: 'Response Model', provider: 'Anthropic', model: 'claude-sonnet-4-20250514', latency: 450, successRate: 98.8, tokenUsage: { input: 128000, output: 38500 }, fallbackCount: 0, status: 'active' },
  { id: 'memory', role: 'memory', name: 'Memory Model', provider: 'OpenAI', model: 'gpt-4o-mini', latency: 180, successRate: 99.5, tokenUsage: { input: 22000, output: 5200 }, fallbackCount: 0, status: 'active' },
  { id: 'filler', role: 'filler', name: 'Filler Model', provider: 'Groq', model: 'llama-3.1-8b', latency: 45, successRate: 97.1, tokenUsage: { input: 8500, output: 2100 }, fallbackCount: 3, status: 'active' },
]

export const mockActivityEvents: ActivityEvent[] = [
  { id: 'a1', type: 'planner', title: 'Plan Created', description: 'Email summary plan with 4 steps', timestamp: m(5), status: 'info' },
  { id: 'a2', type: 'agent', title: 'Gmail Agent Started', description: 'Fetching unread emails', timestamp: m(4), status: 'info' },
  { id: 'a3', type: 'agent', title: 'Gmail Agent Completed', description: '12 emails fetched successfully', timestamp: m(3), status: 'success' },
  { id: 'a4', type: 'agent', title: 'Weather Agent Started', description: 'Checking current weather', timestamp: m(3), status: 'info' },
  { id: 'a5', type: 'agent', title: 'Weather Agent Completed', description: 'Weather data retrieved', timestamp: m(2), status: 'success' },
  { id: 'a6', type: 'memory', title: 'Memory Updated', description: 'Stored email check pattern', timestamp: m(1), status: 'success' },
  { id: 'a7', type: 'queue', title: 'Task Running', description: 'Summarize Content in progress', timestamp: m(1), status: 'info' },
]

export const mockLogs: LogEntry[] = [
  { id: 'l1', source: 'brain', level: 'info', message: 'Brain initialized with response model claude-sonnet-4-20250514', timestamp: h(1) },
  { id: 'l2', source: 'planner', level: 'info', message: 'Plan created: 4 steps for email summary task', timestamp: m(5) },
  { id: 'l3', source: 'agent', level: 'info', message: 'Gmail Agent: Starting email fetch', timestamp: m(4) },
  { id: 'l4', source: 'agent', level: 'debug', message: 'Gmail Agent: API call to gmail.users.messages.list', timestamp: m(4) },
  { id: 'l5', source: 'agent', level: 'info', message: 'Gmail Agent: 12 messages retrieved', timestamp: m(3) },
  { id: 'l6', source: 'memory', level: 'info', message: 'Memory: Storing conversation context (1.2KB)', timestamp: m(2) },
  { id: 'l7', source: 'voice', level: 'info', message: 'TTS: Speaking response (estimated 8.2s)', timestamp: m(1) },
  { id: 'l8', source: 'execution', level: 'warn', message: 'Queue: Task q3 taking longer than expected (>30s)', timestamp: m(1) },
]
