import { FileText, Cpu, Boxes, GitBranch, Activity, Lightbulb } from 'lucide-react'
import StatusChip from './StatusChip'
import { ProgressBar } from './ui'

const LOG_TONE = { success: 'text-emerald-400', warning: 'text-amber-400', info: 'text-sky-400', error: 'text-rose-400', active: 'text-sky-400' }

/**
 * Contents of the ChatShell "Run info" drawer: run configuration, live metrics, an
 * optional progress bar, and the timestamped pipeline log.
 */
export default function RunInfoPanel({ summary, metrics = [], log = [], progress = null, lessons = [] }) {
  return (
    <div className="space-y-5">
      {/* Configuration */}
      <section>
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Configuration</h4>
        <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          <Row icon={FileText} label="Sources" value={`${summary.documents} docs · ${summary.links} links`} />
          <Row icon={Cpu} label="Primary model" value={summary.primaryModelLabel} />
          <Row icon={Boxes} label="Provider" value={summary.providerLabel} />
          <Row icon={GitBranch} label="Mode" value={summary.modeLabel} />
        </div>
      </section>

      {progress && (
        <section>
          <div className="mb-1.5 flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-slate-500"><Activity className="h-3.5 w-3.5" /> Progress</span>
            <span className="tabular-nums text-slate-400">{progress.completed}/{progress.total} · {progress.pct}%</span>
          </div>
          <ProgressBar value={progress.pct} tone={progress.done ? 'success' : 'brand'} />
        </section>
      )}

      {metrics.length > 0 && (
        <section>
          <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Metrics</h4>
          <div className="grid grid-cols-2 gap-2">
            {metrics.map((m) => (
              <div key={m.label} className="rounded-lg border border-slate-200 px-3 py-2">
                <div className="text-lg font-bold tabular-nums text-slate-800">{m.value}</div>
                <div className="text-[11px] text-slate-400">{m.label}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {lessons.length > 0 && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            <Lightbulb className="h-3.5 w-3.5" /> Lessons (deduped) — applied to the next turn
          </h4>
          <ul className="space-y-1.5">
            {lessons.map((l, i) => (
              <li key={i} className="flex items-start gap-2 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs">
                <StatusChip tone={l.kind === 'structural' ? 'warning' : 'brand'} size="xs">
                  {l.kind === 'structural' ? 'finding' : 'promptable'}
                </StatusChip>
                <span className="text-slate-600">{l.text}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Live log</h4>
        <div className="max-h-64 overflow-y-auto rounded-lg bg-navy-900 px-3 py-2 font-mono text-[11px]">
          {log.length === 0 && <div className="py-3 text-center text-slate-500">No events yet.</div>}
          {log.map((l, i) => (
            <div key={i} className="flex items-start gap-1.5 py-0.5">
              <span className="shrink-0 text-slate-500">{l.ts}</span>
              <span className={`shrink-0 ${LOG_TONE[l.status] || 'text-sky-400'}`}>[{l.step}]</span>
              <span className="text-slate-200">{l.message}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

function Row({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center justify-between px-3 py-2">
      <span className="flex items-center gap-2 text-xs text-slate-400"><Icon className="h-3.5 w-3.5" /> {label}</span>
      <span className="truncate text-xs font-semibold text-slate-700">{value}</span>
    </div>
  )
}
