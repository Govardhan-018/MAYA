import { useSettingsStore } from '@/stores/settingsStore'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { motion } from 'framer-motion'
import { Palette, Volume2, Cpu, Gauge, ScrollText, Bell, Code } from 'lucide-react'

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={`w-10 h-5 rounded-full transition-colors ${value ? 'bg-maya-cyan' : 'bg-maya-bg-tertiary'}`}
    >
      <motion.div
        className="w-4 h-4 rounded-full bg-white shadow-sm"
        animate={{ x: value ? 21 : 2 }}
        transition={{ duration: 0.15 }}
      />
    </button>
  )
}

export function SettingsPage() {
  const settings = useSettingsStore()

  return (
    <div className="p-6 h-full overflow-y-auto">
      <PageHeader title="Settings" subtitle="Configure MAYA system preferences" />

      <div className="max-w-2xl space-y-4">
        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-4">
            <Palette size={14} className="text-maya-cyan" /> Theme
          </h3>
          <div className="flex gap-3">
            {(['dark', 'light'] as const).map((theme) => (
              <button
                key={theme}
                onClick={() => settings.setSetting('theme', theme)}
                className={`px-4 py-2 rounded-lg border text-sm capitalize transition-all ${
                  settings.theme === theme
                    ? 'border-maya-cyan bg-maya-cyan/10 text-maya-cyan'
                    : 'border-maya-border text-maya-text-muted hover:text-maya-text'
                }`}
              >
                {theme}
              </button>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-4">
            <Bell size={14} className="text-maya-orange" /> Notifications
          </h3>
          <div className="flex items-center justify-between">
            <span className="text-sm text-maya-text-secondary">Enable notifications</span>
            <Toggle value={settings.notifications} onChange={(v) => settings.setSetting('notifications', v)} />
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-4">
            <Gauge size={14} className="text-maya-green" /> Performance
          </h3>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm text-maya-text-secondary block">Performance Mode</span>
              <span className="text-xs text-maya-text-muted">Reduces animations for better performance</span>
            </div>
            <Toggle value={settings.performanceMode} onChange={(v) => settings.setSetting('performanceMode', v)} />
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-4">
            <ScrollText size={14} className="text-maya-purple" /> Logging
          </h3>
          <div className="flex gap-2">
            {(['debug', 'info', 'warn', 'error'] as const).map((level) => (
              <button
                key={level}
                onClick={() => settings.setSetting('logLevel', level)}
                className={`px-3 py-1.5 rounded-lg border text-xs uppercase transition-all ${
                  settings.logLevel === level
                    ? 'border-maya-cyan bg-maya-cyan/10 text-maya-cyan'
                    : 'border-maya-border text-maya-text-muted hover:text-maya-text'
                }`}
              >
                {level}
              </button>
            ))}
          </div>
        </GlassPanel>

        <GlassPanel>
          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-4">
            <Code size={14} className="text-maya-red" /> Developer
          </h3>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm text-maya-text-secondary block">Developer Mode</span>
              <span className="text-xs text-maya-text-muted">Show advanced debugging tools and raw data</span>
            </div>
            <Toggle value={settings.developerMode} onChange={(v) => settings.setSetting('developerMode', v)} />
          </div>
        </GlassPanel>
      </div>
    </div>
  )
}
