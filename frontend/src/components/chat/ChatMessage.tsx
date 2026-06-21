import { motion } from 'framer-motion'
import { User, Bot, Terminal, Brain, Mic, Hexagon } from 'lucide-react'
import type { ChatMessage as ChatMessageType } from '@/types'

const roleConfig = {
  user: { icon: User, color: 'text-maya-blue', bg: 'bg-maya-blue/10', border: 'border-maya-blue/20', label: 'You' },
  assistant: { icon: Hexagon, color: 'text-maya-cyan', bg: 'bg-maya-cyan/10', border: 'border-maya-cyan/20', label: 'MAYA' },
  system: { icon: Terminal, color: 'text-maya-text-muted', bg: 'bg-white/5', border: 'border-white/10', label: 'System' },
  agent: { icon: Bot, color: 'text-maya-green', bg: 'bg-maya-green/10', border: 'border-maya-green/20', label: 'Agent' },
  planner: { icon: Brain, color: 'text-maya-purple', bg: 'bg-maya-purple/10', border: 'border-maya-purple/20', label: 'Planner' },
  voice: { icon: Mic, color: 'text-maya-orange', bg: 'bg-maya-orange/10', border: 'border-maya-orange/20', label: 'Voice' },
}

export function ChatMessageBubble({ message }: { message: ChatMessageType }) {
  const config = roleConfig[message.role]
  const Icon = config.icon
  const isUser = message.role === 'user'

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      <div className={`w-8 h-8 rounded-lg ${config.bg} border ${config.border} flex items-center justify-center flex-shrink-0`}>
        <Icon size={16} className={config.color} />
      </div>
      <div className={`max-w-[75%] ${isUser ? 'text-right' : ''}`}>
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-medium ${config.color}`}>
            {message.agentName || config.label}
          </span>
          <span className="text-[10px] text-maya-text-muted">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
        <div className={`
          rounded-xl px-4 py-2.5 text-sm leading-relaxed
          ${isUser
            ? 'bg-maya-blue/15 border border-maya-blue/20 text-maya-text'
            : `${config.bg} border ${config.border} text-maya-text`
          }
        `}>
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    </motion.div>
  )
}
