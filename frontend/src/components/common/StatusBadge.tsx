interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

const statusColors: Record<string, string> = {
  idle: 'bg-maya-text-muted',
  running: 'bg-maya-cyan',
  completed: 'bg-maya-green',
  success: 'bg-maya-green',
  failed: 'bg-maya-red',
  error: 'bg-maya-red',
  pending: 'bg-maya-orange',
  cancelled: 'bg-maya-text-muted',
  active: 'bg-maya-green',
  paused: 'bg-maya-orange',
  archived: 'bg-maya-text-muted',
  disabled: 'bg-maya-text-muted',
  online: 'bg-maya-green',
  offline: 'bg-maya-red',
  connected: 'bg-maya-green',
  disconnected: 'bg-maya-red',
  listening: 'bg-maya-cyan',
  thinking: 'bg-maya-purple',
  planning: 'bg-maya-blue',
  executing: 'bg-maya-orange',
  speaking: 'bg-maya-green',
  info: 'bg-maya-blue',
  warning: 'bg-maya-orange',
  warn: 'bg-maya-orange',
  debug: 'bg-maya-text-muted',
  fallback: 'bg-maya-orange',
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const color = statusColors[status] || 'bg-maya-text-muted'
  const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5'
  const isAnimated = ['running', 'listening', 'thinking', 'planning', 'executing', 'speaking'].includes(status)

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`${dotSize} rounded-full ${color} ${isAnimated ? 'animate-pulse' : ''}`} />
      <span className="text-xs text-maya-text-secondary capitalize">{status}</span>
    </span>
  )
}
