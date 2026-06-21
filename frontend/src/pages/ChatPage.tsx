import { useEffect, useRef } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { useQueueStore } from '@/stores/queueStore'
import { MayaOrb } from '@/components/orb/MayaOrb'
import { ChatMessageBubble } from '@/components/chat/ChatMessage'
import { ChatInput } from '@/components/chat/ChatInput'
import { PlannerWidget } from '@/components/planner/PlannerWidget'
import { VoiceVisualizer } from '@/components/voice/VoiceVisualizer'

export function ChatPage() {
  const messages = useChatStore((s) => s.messages)
  const plan = useQueueStore((s) => s.currentPlan)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div className="h-full flex flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center">
            <MayaOrb size={140} />
            <p className="text-maya-text-secondary text-sm mt-6">How can I help you today?</p>
          </div>
        ) : (
          <div className="px-6 py-4 space-y-4">
            {messages.map((msg) => (
              <ChatMessageBubble key={msg.id} message={msg} />
            ))}
          </div>
        )}
      </div>
      {plan && <PlannerWidget />}
      <VoiceVisualizer />
      <ChatInput />
    </div>
  )
}
