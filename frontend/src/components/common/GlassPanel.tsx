import { type ReactNode } from 'react'
import { motion } from 'framer-motion'

interface GlassPanelProps {
  children: ReactNode
  className?: string
  hover?: boolean
  padding?: boolean
}

export function GlassPanel({ children, className = '', hover = false, padding = true }: GlassPanelProps) {
  return (
    <motion.div
      className={`
        rounded-xl border border-maya-border bg-maya-surface backdrop-blur-md
        ${hover ? 'hover:border-maya-border-active hover:bg-maya-surface-hover transition-colors' : ''}
        ${padding ? 'p-4' : ''}
        ${className}
      `}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {children}
    </motion.div>
  )
}
