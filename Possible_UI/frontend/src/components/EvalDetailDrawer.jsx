import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X, Cpu, Lightbulb } from 'lucide-react'
import StatusChip from './StatusChip'
import EvaluationCard from './EvaluationCard'
import { verdictTone, verdictLabel } from '../lib/tone'

/**
 * Slide-over drawer with the full evaluation details, shown over the chat (no navigation).
 * Evaluator details + current lessons on top, then the full EvaluationCard (rubric &
 * violations, findings, evidence, summary, answers).
 */
export default function EvalDetailDrawer({ open, onClose, evaluation: e, lessons = [] }) {
  useEffect(() => {
    if (!open) return
    const onKey = (ev) => ev.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !e) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-navy-900/40 backdrop-blur-sm" onClick={onClose} />
      <aside className="relative flex h-full w-[580px] max-w-[95vw] animate-fade-in flex-col border-l border-slate-200 bg-slate-50 shadow-panel">
        <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-5 py-3">
          <span className="text-sm font-semibold text-slate-900">Evaluation details</span>
          <StatusChip tone={verdictTone(e.verdict)} size="xs" dot>{verdictLabel(e.verdict)}</StatusChip>
          {e.gatedBy && <StatusChip tone="danger" size="xs">gated by {e.gatedBy.replace(/_/g, ' ')}</StatusChip>}
          <button onClick={onClose} className="focusable ml-auto rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <Cpu className="h-3.5 w-3.5 text-slate-400" /> Evaluator details
            </div>
            <dl className="space-y-1 text-xs text-slate-600">
              {typeof e.overall === 'number' && (
                <Row label="Overall" value={<span className="font-medium text-slate-700">{e.overall.toFixed(2)}{e.failed ? ' (FAIL)' : ''}</span>} />
              )}
              {e.gatedBy && <Row label="Gated by" value={<StatusChip tone="danger" size="xs">{e.gatedBy.replace(/_/g, ' ')}</StatusChip>} />}
              <Row label="Reasoning" value={<span className="text-slate-700">{e.reasoningQuality}</span>} />
              {e.evaluatorAgent?.model && <Row label="Judged by" value={<span className="font-mono text-[11px] text-slate-700">{e.evaluatorAgent.model}</span>} />}
              {e.providerAgent?.model && <Row label="Provider" value={<span className="font-mono text-[11px] text-slate-700">{e.providerAgent.model}</span>} />}
              {e.sameFamilyJudge && <Row label="Bias flag" value={<StatusChip tone="warning" size="xs">same-family judge</StatusChip>} />}
            </dl>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <Lightbulb className="h-3.5 w-3.5 text-slate-400" /> Lessons in play
              <StatusChip tone="neutral" size="xs">{lessons.length}</StatusChip>
            </div>
            {lessons.length ? (
              <ul className="space-y-1.5">
                {lessons.map((l, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs">
                    <StatusChip tone={l.kind === 'structural' ? 'warning' : 'brand'} size="xs">
                      {l.kind === 'structural' ? 'finding' : 'promptable'}
                    </StatusChip>
                    <span className="text-slate-600">{l.text}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="text-xs text-slate-400">No lessons yet — they appear after the first evaluated turn.</span>
            )}
          </div>

          <EvaluationCard evaluation={e} />
        </div>
      </aside>
    </div>,
    document.body,
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-slate-400">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}
