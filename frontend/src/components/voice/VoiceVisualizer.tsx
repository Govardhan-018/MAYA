import { motion } from 'framer-motion'
import { useVoiceStore } from '@/stores/voiceStore'
import { useUIStore } from '@/stores/uiStore'

export function VoiceVisualizer() {
  const waveformData = useVoiceStore((s) => s.waveformData)
  const micLevel = useVoiceStore((s) => s.micLevel)
  const listening = useVoiceStore((s) => s.listening)
  const mayaState = useUIStore((s) => s.mayaState)

  const stateLabel = mayaState === 'listening' ? 'Listening...'
    : mayaState === 'thinking' ? 'Thinking...'
    : mayaState === 'speaking' ? 'Speaking...'
    : listening ? 'Listening...' : ''

  if (!listening && mayaState === 'idle') return null

  return (
    <div className="px-6 py-3">
      <div className="flex items-center gap-3 rounded-xl border border-maya-border bg-maya-surface/50 backdrop-blur-md px-4 py-3">
        <div className="relative w-3 h-3">
          <div className={`absolute inset-0 rounded-full ${listening ? 'bg-maya-cyan animate-pulse' : 'bg-maya-text-muted'}`} />
          {listening && (
            <motion.div
              className="absolute inset-0 rounded-full border border-maya-cyan"
              animate={{ scale: [1, 2], opacity: [0.6, 0] }}
              transition={{ duration: 1.5, repeat: Infinity }}
            />
          )}
        </div>

        <div className="flex-1 flex items-end gap-[2px] h-8">
          {waveformData.slice(0, 48).map((value, i) => (
            <motion.div
              key={i}
              className="flex-1 rounded-full bg-maya-cyan/60"
              animate={{ height: Math.max(2, value * 32) }}
              transition={{ duration: 0.1 }}
            />
          ))}
        </div>

        <div className="flex flex-col items-end gap-1">
          {stateLabel && (
            <span className="text-xs text-maya-cyan font-medium">{stateLabel}</span>
          )}
          <div className="flex items-center gap-1">
            <div className="w-12 h-1 rounded-full bg-maya-bg-tertiary overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-maya-cyan"
                animate={{ width: `${micLevel * 100}%` }}
                transition={{ duration: 0.1 }}
              />
            </div>
            <span className="text-[10px] text-maya-text-muted">{Math.round(micLevel * 100)}%</span>
          </div>
        </div>
      </div>
    </div>
  )
}
