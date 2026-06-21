import { useState } from 'react'
import { motion } from 'framer-motion'
import { GlassPanel } from '@/components/common/GlassPanel'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { mockProjects } from '@/services/mockData'
import {
  FolderKanban, Target, AlertTriangle, FileText, Calendar,
  TrendingUp, ChevronRight, Flag,
} from 'lucide-react'

const severityColors = {
  low: 'text-maya-green',
  medium: 'text-maya-orange',
  high: 'text-maya-red',
  critical: 'text-maya-red',
}

export function ProjectsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const projects = mockProjects
  const selected = projects.find((p) => p.id === selectedId)

  return (
    <div className="h-full flex">
      <div className="flex-1 p-6 overflow-y-auto">
        <PageHeader title="Projects" subtitle={`${projects.length} active projects`} />

        <div className="space-y-4">
          {projects.map((project, i) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <GlassPanel hover className="cursor-pointer" onClick={() => setSelectedId(project.id)}>
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-maya-purple/10 border border-maya-purple/20 flex items-center justify-center flex-shrink-0">
                    <FolderKanban size={20} className="text-maya-purple" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-medium text-maya-text">{project.name}</h3>
                      <StatusBadge status={project.status} />
                    </div>
                    <p className="text-xs text-maya-text-secondary mt-1">{project.description}</p>
                    <div className="mt-3 flex items-center gap-4">
                      <div className="flex-1 max-w-48">
                        <div className="flex items-center justify-between text-[10px] text-maya-text-muted mb-1">
                          <span>Progress</span>
                          <span>{project.progress}%</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-maya-bg-tertiary overflow-hidden">
                          <div className="h-full rounded-full bg-maya-cyan" style={{ width: `${project.progress}%` }} />
                        </div>
                      </div>
                      <span className="text-[11px] text-maya-text-muted flex items-center gap-1">
                        <Target size={10} /> {project.milestones.filter((m) => m.completed).length}/{project.milestones.length}
                      </span>
                      <span className="text-[11px] text-maya-text-muted flex items-center gap-1">
                        <AlertTriangle size={10} /> {project.risks.filter((r) => !r.mitigated).length} risks
                      </span>
                    </div>
                  </div>
                  <ChevronRight size={14} className="text-maya-text-muted mt-3" />
                </div>
              </GlassPanel>
            </motion.div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="w-[400px] border-l border-maya-border bg-maya-bg-secondary/50 overflow-y-auto p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-maya-text">{selected.name}</h2>
            <button onClick={() => setSelectedId(null)} className="text-maya-text-muted hover:text-maya-text text-xs">Close</button>
          </div>

          <div className="mb-6">
            <div className="flex items-center justify-between text-xs mb-2">
              <span className="text-maya-text-secondary">Overall Progress</span>
              <span className="text-maya-cyan font-medium">{selected.progress}%</span>
            </div>
            <div className="h-2 rounded-full bg-maya-bg-tertiary overflow-hidden">
              <div className="h-full rounded-full bg-gradient-to-r from-maya-cyan to-maya-blue" style={{ width: `${selected.progress}%` }} />
            </div>
          </div>

          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-3">
            <Target size={14} /> Milestones
          </h3>
          <div className="space-y-2 mb-6">
            {selected.milestones.map((m) => (
              <div key={m.id} className="flex items-center gap-2 text-xs">
                <div className={`w-3 h-3 rounded border ${m.completed ? 'bg-maya-green border-maya-green' : 'border-maya-border'}`} />
                <span className={m.completed ? 'text-maya-text-muted line-through' : 'text-maya-text'}>{m.name}</span>
                <span className="text-maya-text-muted ml-auto">{new Date(m.dueDate).toLocaleDateString()}</span>
              </div>
            ))}
          </div>

          <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-3">
            <Flag size={14} /> Risks
          </h3>
          <div className="space-y-2 mb-6">
            {selected.risks.map((r) => (
              <div key={r.id} className="rounded-lg border border-maya-border bg-maya-surface/30 p-2.5">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={12} className={severityColors[r.severity]} />
                  <span className="text-xs text-maya-text">{r.description}</span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-[10px] capitalize ${severityColors[r.severity]}`}>{r.severity}</span>
                  {r.mitigated && <span className="text-[10px] text-maya-green">Mitigated</span>}
                </div>
              </div>
            ))}
          </div>

          {selected.notes.length > 0 && (
            <>
              <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-3">
                <FileText size={14} /> Notes
              </h3>
              <div className="space-y-1 mb-6">
                {selected.notes.map((note, i) => (
                  <p key={i} className="text-xs text-maya-text-secondary">- {note}</p>
                ))}
              </div>
            </>
          )}

          {selected.meetings.length > 0 && (
            <>
              <h3 className="text-sm font-medium text-maya-text flex items-center gap-2 mb-3">
                <Calendar size={14} /> Meetings
              </h3>
              <div className="space-y-2">
                {selected.meetings.map((meeting) => (
                  <div key={meeting.id} className="rounded-lg border border-maya-border bg-maya-surface/30 p-2.5">
                    <span className="text-xs font-medium text-maya-text">{meeting.title}</span>
                    <span className="text-[10px] text-maya-text-muted block">{new Date(meeting.date).toLocaleDateString()}</span>
                    <span className="text-[10px] text-maya-text-secondary">{meeting.notes}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="mt-6 flex items-center gap-3 text-[11px] text-maya-text-muted">
            <TrendingUp size={12} />
            <span>Updated {new Date(selected.updatedAt).toLocaleString()}</span>
          </div>
        </div>
      )}
    </div>
  )
}
