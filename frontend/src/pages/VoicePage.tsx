import { motion } from 'framer-motion'
import { useVoiceStore } from '@/stores/voiceStore'
import { useUIStore } from '@/stores/uiStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { Mic, MicOff, Radio, Volume2, Zap, MessageSquare, AlertCircle } from 'lucide-react'
import { ipcInvoke } from '@/services/ipc'

export function VoicePage() {
  const voice = useVoiceStore()
  const mayaState = useUIStore((s) => s.mayaState)

  const modeLabels = {
    push_to_talk: 'Push to Talk',
    wake_word: 'Wake Word',
    continuous: 'Continuous',
    off: 'Off',
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Voice Control" subtitle="Manage voice input and speech settings" />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text mb-4 flex items-center gap-2">
            <Mic size={14} className="text-maya-cyan" /> Voice Status
          </h3>
          <div className="flex items-center gap-6 mb-4">
            <div className="relative">
              <motion.div
                className={`w-20 h-20 rounded-full flex items-center justify-center border-2 ${
                  voice.listening ? 'border-maya-cyan bg-maya-cyan/10' : 'border-maya-border bg-maya-surface'
                }`}
                animate={voice.listening ? { scale: [1, 1.05, 1] } : {}}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                {voice.listening ? (
                  <Mic size={32} className="text-maya-cyan" />
                ) : (
                  <MicOff size={32} className="text-maya-text-muted" />
                )}
              </motion.div>
              {voice.listening && (
                <motion.div
                  className="absolute inset-0 rounded-full border border-maya-cyan"
                  animate={{ scale: [1, 1.5], opacity: [0.5, 0] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
              )}
            </div>
            <div>
              <StatusBadge status={voice.listening ? 'listening' : 'idle'} size="md" />
              <p className="text-xs text-maya-text-secondary mt-2">Mode: {modeLabels[voice.mode]}</p>
              <p className="text-xs text-maya-text-secondary">Mic: {voice.microphone}</p>
            </div>
          </div>

          <div className="mb-4">
            <span className="text-xs text-maya-text-muted block mb-2">Mic Level</span>
            <div className="h-2 rounded-full bg-maya-bg-tertiary overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-maya-cyan"
                animate={{ width: `${voice.micLevel * 100}%` }}
                transition={{ duration: 0.1 }}
              />
            </div>
          </div>

          <div className="flex items-end gap-[2px] h-16 rounded-lg border border-maya-border bg-maya-bg/50 p-2">
            {voice.waveformData.slice(0, 48).map((value, i) => (
              <motion.div
                key={i}
                className="flex-1 rounded-full bg-maya-cyan/50"
                animate={{ height: Math.max(2, value * 48) }}
                transition={{ duration: 0.1 }}
              />
            ))}
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text mb-4 flex items-center gap-2">
            <Radio size={14} className="text-maya-purple" /> Voice Mode
          </h3>
          <div className="space-y-2">
            {(Object.entries(modeLabels) as [keyof typeof modeLabels, string][]).map(([mode, label]) => (
              <button
                key={mode}
                onClick={() => ipcInvoke('set_voice_mode', { mode })}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border transition-all text-left ${
                  voice.mode === mode
                    ? 'border-maya-cyan bg-maya-cyan/10 text-maya-cyan'
                    : 'border-maya-border bg-maya-surface text-maya-text-secondary hover:text-maya-text'
                }`}
              >
                <Radio size={14} />
                <span className="text-sm">{label}</span>
              </button>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text mb-4 flex items-center gap-2">
            <Volume2 size={14} className="text-maya-green" /> Speech Settings
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare size={14} className="text-maya-text-muted" />
                <span className="text-sm text-maya-text">Conversation Mode</span>
              </div>
              <button
                onClick={() => ipcInvoke('toggle_conversation_mode')}
                className={`w-10 h-5 rounded-full transition-colors ${voice.conversationMode ? 'bg-maya-cyan' : 'bg-maya-bg-tertiary'}`}
              >
                <motion.div
                  className="w-4 h-4 rounded-full bg-white shadow-sm"
                  animate={{ x: voice.conversationMode ? 21 : 2 }}
                  transition={{ duration: 0.15 }}
                />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap size={14} className="text-maya-text-muted" />
                <span className="text-sm text-maya-text">Filler Voice</span>
              </div>
              <button
                onClick={() => ipcInvoke('toggle_filler')}
                className={`w-10 h-5 rounded-full transition-colors ${voice.fillerEnabled ? 'bg-maya-cyan' : 'bg-maya-bg-tertiary'}`}
              >
                <motion.div
                  className="w-4 h-4 rounded-full bg-white shadow-sm"
                  animate={{ x: voice.fillerEnabled ? 21 : 2 }}
                  transition={{ duration: 0.15 }}
                />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle size={14} className="text-maya-text-muted" />
                <span className="text-sm text-maya-text">Interrupt Detection</span>
              </div>
              <button
                onClick={() => ipcInvoke('toggle_interrupt')}
                className={`w-10 h-5 rounded-full transition-colors ${voice.interruptEnabled ? 'bg-maya-cyan' : 'bg-maya-bg-tertiary'}`}
              >
                <motion.div
                  className="w-4 h-4 rounded-full bg-white shadow-sm"
                  animate={{ x: voice.interruptEnabled ? 21 : 2 }}
                  transition={{ duration: 0.15 }}
                />
              </button>
            </div>
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text mb-4 flex items-center gap-2">
            <Volume2 size={14} className="text-maya-orange" /> Speech Queue
          </h3>
          {voice.speechQueue.length === 0 ? (
            <p className="text-xs text-maya-text-muted">No speech queued</p>
          ) : (
            <div className="space-y-2">
              {voice.speechQueue.map((text, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-maya-text-muted">{i + 1}.</span>
                  <span className="text-maya-text truncate">{text}</span>
                </div>
              ))}
            </div>
          )}
        </GlassPanel>
      </div>
    </div>
  )
}
