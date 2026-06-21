import { useState, type KeyboardEvent } from 'react'
import { Send, Mic } from 'lucide-react'
import { useChatStore } from '@/stores/chatStore'
import { ipcInvoke } from '@/services/ipc'

export function ChatInput() {
  const { inputText, setInputText } = useChatStore()
  const [isSending, setIsSending] = useState(false)

  const sendMessage = async () => {
    const text = inputText.trim()
    if (!text || isSending) return

    setIsSending(true)
    useChatStore.getState().addMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    })
    setInputText('')

    await ipcInvoke('send_message', { text })
    setIsSending(false)
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="px-6 pb-4 pt-2">
      <div className="flex items-end gap-2 rounded-xl border border-maya-border bg-maya-surface backdrop-blur-md p-2 focus-within:border-maya-border-active transition-colors">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask MAYA anything..."
          rows={1}
          className="flex-1 bg-transparent text-sm text-maya-text placeholder:text-maya-text-muted resize-none outline-none px-2 py-1.5 max-h-32"
          style={{ minHeight: '36px' }}
        />
        <button
          onClick={() => ipcInvoke('toggle_voice')}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-maya-text-muted hover:text-maya-cyan hover:bg-maya-cyan/10 transition-all"
        >
          <Mic size={16} />
        </button>
        <button
          onClick={sendMessage}
          disabled={!inputText.trim() || isSending}
          className="w-8 h-8 rounded-lg flex items-center justify-center bg-maya-cyan/20 text-maya-cyan hover:bg-maya-cyan/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
