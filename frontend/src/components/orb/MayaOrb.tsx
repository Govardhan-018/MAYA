import { motion } from 'framer-motion'
import { useUIStore } from '@/stores/uiStore'

const stateConfig = {
  idle: {
    gradient: ['#22d3ee', '#3b82f6'],
    shadow: 'rgba(34, 211, 238, 0.3)',
    scale: [1, 1.02, 1],
    duration: 4,
  },
  listening: {
    gradient: ['#22d3ee', '#06b6d4'],
    shadow: 'rgba(34, 211, 238, 0.5)',
    scale: [1, 1.08, 1],
    duration: 1.5,
  },
  thinking: {
    gradient: ['#a855f7', '#7c3aed'],
    shadow: 'rgba(168, 85, 247, 0.4)',
    scale: [1, 1.05, 0.97, 1],
    duration: 2,
  },
  planning: {
    gradient: ['#3b82f6', '#2563eb'],
    shadow: 'rgba(59, 130, 246, 0.4)',
    scale: [1, 1.04, 1],
    duration: 1.8,
  },
  executing: {
    gradient: ['#f59e0b', '#d97706'],
    shadow: 'rgba(245, 158, 11, 0.4)',
    scale: [1, 1.06, 0.98, 1],
    duration: 1,
  },
  speaking: {
    gradient: ['#10b981', '#059669'],
    shadow: 'rgba(16, 185, 129, 0.4)',
    scale: [1, 1.1, 0.95, 1.05, 1],
    duration: 0.8,
  },
  error: {
    gradient: ['#ef4444', '#dc2626'],
    shadow: 'rgba(239, 68, 68, 0.4)',
    scale: [1, 1.03, 1],
    duration: 2,
  },
}

export function MayaOrb({ size = 160 }: { size?: number }) {
  const mayaState = useUIStore((s) => s.mayaState)
  const config = stateConfig[mayaState]
  const ringCount = 3

  return (
    <div className="relative flex items-center justify-center" style={{ width: size * 1.8, height: size * 1.8 }}>
      {Array.from({ length: ringCount }).map((_, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full border"
          style={{
            width: size + (i + 1) * 40,
            height: size + (i + 1) * 40,
            borderColor: `${config.gradient[0]}${(15 - i * 4).toString(16).padStart(2, '0')}`,
          }}
          animate={{
            rotate: i % 2 === 0 ? 360 : -360,
            scale: [1, 1.02, 1],
          }}
          transition={{
            rotate: { duration: 20 + i * 10, repeat: Infinity, ease: 'linear' },
            scale: { duration: config.duration * 2, repeat: Infinity, ease: 'easeInOut' },
          }}
        />
      ))}

      <motion.div
        className="absolute rounded-full opacity-30 blur-xl"
        style={{
          width: size * 1.4,
          height: size * 1.4,
          background: `radial-gradient(circle, ${config.gradient[0]}, transparent)`,
        }}
        animate={{ scale: config.scale, opacity: [0.2, 0.35, 0.2] }}
        transition={{ duration: config.duration, repeat: Infinity, ease: 'easeInOut' }}
      />

      <motion.div
        className="relative rounded-full flex items-center justify-center"
        style={{
          width: size,
          height: size,
          background: `radial-gradient(circle at 35% 35%, ${config.gradient[0]}dd, ${config.gradient[1]}bb, ${config.gradient[1]}44)`,
          boxShadow: `0 0 ${size / 3}px ${config.shadow}, inset 0 0 ${size / 4}px rgba(255,255,255,0.1)`,
        }}
        animate={{ scale: config.scale }}
        transition={{ duration: config.duration, repeat: Infinity, ease: 'easeInOut' }}
      >
        <div
          className="absolute inset-1 rounded-full"
          style={{
            background: `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.2), transparent 60%)`,
          }}
        />
        <motion.span
          className="text-white/80 text-xs font-medium uppercase tracking-widest select-none"
          animate={{ opacity: [0.6, 1, 0.6] }}
          transition={{ duration: config.duration, repeat: Infinity }}
        >
          {mayaState}
        </motion.span>
      </motion.div>
    </div>
  )
}
