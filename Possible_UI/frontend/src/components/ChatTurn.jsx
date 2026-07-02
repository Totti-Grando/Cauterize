import { useState } from 'react'
import { Loader2, ScanSearch, PanelRightOpen } from 'lucide-react'
import ChatBubble from './ChatBubble'
import EvalDetailDrawer from './EvalDetailDrawer'
import StatusChip from './StatusChip'
import { verdictTone, verdictLabel, groundedLabel } from '../lib/tone'

/**
 * One chat turn: the user's question, the provider's answer, and a compact evaluation
 * strip. "Details" opens a slide-over drawer (over the chat) with the rubric/violations,
 * evaluator info, and current lessons — no navigation away.
 */
export default function ChatTurn({ turn, evaluatorLabel = 'the evaluator', lessons = [] }) {
  const [detailsOpen, setDetailsOpen] = useState(false)
  const e = turn.evaluation
  const nChecks = (e?.rubric || []).reduce((n, g) => n + g.checks.length, 0)
  const nPass = (e?.rubric || []).reduce((n, g) => n + g.checks.filter((c) => c.score === 1).length, 0)

  return (
    <div className="space-y-3">
      {turn.original && (
        <div className="ml-auto max-w-[85%] rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800">
          <span className="font-semibold">Attack escalation</span> of your message:{' '}
          <span className="italic">"{turn.original}"</span> — the probe below is what was sent to the provider.
        </div>
      )}
      <ChatBubble role="question" time="">{turn.question}</ChatBubble>

      {turn.answer ? (
        <ChatBubble role="answer" author={turn.provider || 'Provider'} time="">
          {turn.answer}
        </ChatBubble>
      ) : (
        <ChatBubble role="answer" author="Provider">
          <span className="inline-flex items-center gap-2 text-slate-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> thinking…
          </span>
        </ChatBubble>
      )}

      {/* Evaluation strip — click to open the details slide-over over the chat */}
      {e ? (
        <div className="ml-1">
          <button
            onClick={() => setDetailsOpen(true)}
            className="focusable inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
          >
            <ScanSearch className="h-3.5 w-3.5 text-violet-500" />
            <span>Evaluated by {evaluatorLabel}:</span>
            <StatusChip tone={verdictTone(e.verdict)} size="xs" dot>{verdictLabel(e.verdict)}</StatusChip>
            {nChecks > 0 && (
              <span className="text-slate-400">
                · {nPass}/{nChecks} checks{e.gatedBy ? ` · gated by ${e.gatedBy.replace(/_/g, ' ')}` : ''}
              </span>
            )}
            <span className="ml-1 inline-flex items-center gap-1 font-medium text-brand-700">
              Details <PanelRightOpen className="h-3.5 w-3.5" />
            </span>
          </button>
          <EvalDetailDrawer
            open={detailsOpen}
            onClose={() => setDetailsOpen(false)}
            evaluation={e}
            lessons={lessons}
          />
        </div>
      ) : turn.answer ? (
        <div className="ml-1 inline-flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> evaluating…
        </div>
      ) : null}
    </div>
  )
}
