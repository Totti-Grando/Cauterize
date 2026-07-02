import { useState } from 'react'
import { ChevronRight, Target, MessageSquareQuote, Braces, Link2, FileText, Tag, ScanSearch, Check, X } from 'lucide-react'
import StatusChip from './StatusChip'
import JsonViewer from './JsonViewer'
import { verdictTone, verdictLabel, groundedTone, groundedLabel, shortfallTone, prettyTag } from '../lib/tone'

const TIER_TONE = { critical: 'danger', major: 'warning', minor: 'neutral' }

const BAND = {
  success: 'border-l-emerald-500',
  warning: 'border-l-amber-500',
  danger: 'border-l-rose-500',
  info: 'border-l-sky-500',
  neutral: 'border-l-slate-400',
}

function Section({ icon: Icon, title, badge, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-slate-100 first:border-t-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="focusable flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-slate-50"
      >
        <ChevronRight className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-90' : ''}`} />
        <Icon className="h-4 w-4 text-slate-400" />
        <span className="text-xs font-semibold text-slate-700">{title}</span>
        {badge != null && <span className="ml-auto">{badge}</span>}
      </button>
      {open && <div className="px-4 pb-4 pl-10 text-sm text-slate-600">{children}</div>}
    </div>
  )
}

// The colored evaluation card displayed beneath each provider answer.
export default function EvaluationCard({ evaluation: e }) {
  const tone = verdictTone(e.verdict)
  return (
    <div className={`overflow-hidden rounded-xl border border-slate-200 border-l-4 bg-white shadow-card ${BAND[tone]}`}>
      <div className="flex flex-wrap items-center gap-2 px-4 py-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evaluation</span>
        <StatusChip tone={tone} dot>
          {verdictLabel(e.verdict)}
        </StatusChip>
        <StatusChip tone={groundedTone(e.sourceGroundedness)}>
          Source: {groundedLabel(e.sourceGroundedness)}
        </StatusChip>
        <StatusChip tone={e.grounded ? 'success' : 'danger'}>Grounded: {String(e.grounded)}</StatusChip>
        <span className="ml-auto text-xs text-slate-400">Reasoning: {e.reasoningQuality}</span>
      </div>

      {e.shortfalls?.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-100 px-4 py-2.5">
          <Tag className="h-3.5 w-3.5 text-slate-400" />
          {e.shortfalls.map((s) => (
            <StatusChip key={s} tone={shortfallTone(s)} size="xs">
              {prettyTag(s)}
            </StatusChip>
          ))}
        </div>
      )}

      <div className="px-4 pb-3 pt-1">
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">{e.finalSummary}</p>
      </div>

      <Section icon={Target} title="Expected answer">
        {e.expectedAnswer}
      </Section>
      <Section icon={MessageSquareQuote} title="Provider answer">
        {e.providerAnswer}
      </Section>
      <Section
        icon={FileText}
        title="Findings (missing / incorrect / extra)"
        badge={
          <StatusChip tone="neutral" size="xs">
            {e.missingPoints.length + e.incorrectPoints.length + e.extraPoints.length}
          </StatusChip>
        }
      >
        <PointList label="Missing" tone="warning" items={e.missingPoints} />
        <PointList label="Incorrect" tone="danger" items={e.incorrectPoints} />
        <PointList label="Extra" tone="info" items={e.extraPoints} />
      </Section>
      <Section
        icon={Link2}
        title="Source evidence & links"
        badge={<StatusChip tone="neutral" size="xs">{e.evidence.length}</StatusChip>}
      >
        <ul className="space-y-1.5">
          {e.evidence.map((ev) => (
            <li key={ev.id} className="flex items-center justify-between gap-2 rounded-md border border-slate-200 px-2.5 py-1.5">
              <span className="truncate text-xs text-slate-600">{ev.title}</span>
              <StatusChip tone={ev.fetchSuccess ? 'success' : 'warning'} size="xs">
                {ev.fetchSuccess ? `${ev.textLength} chars` : 'login / blocked'}
              </StatusChip>
            </li>
          ))}
          {e.evidence.length === 0 && <li className="text-xs text-slate-400">No evidence captured for this answer.</li>}
        </ul>
      </Section>
      {e.rubric?.length > 0 && (
        <Section
          icon={ScanSearch}
          title="Evaluator details — rubric"
          defaultOpen
          badge={<StatusChip tone="neutral" size="xs">
            {e.rubric.reduce((n, g) => n + g.checks.length, 0)} checks
          </StatusChip>}
        >
          <RubricBreakdown rubric={e.rubric} perDimension={e.perDimension} gatedBy={e.gatedBy} />
        </Section>
      )}
      <Section icon={Braces} title="Evaluation JSON">
        <JsonViewer
          data={{
            verdict: e.verdict,
            grounded: e.grounded,
            source_groundedness: e.sourceGroundedness,
            shortfalls: e.shortfalls,
            reasoning_quality: e.reasoningQuality,
            missing_points: e.missingPoints,
            incorrect_points: e.incorrectPoints,
          }}
        />
      </Section>
    </div>
  )
}

function RubricBreakdown({ rubric, perDimension, gatedBy }) {
  return (
    <div className="space-y-3">
      {gatedBy && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs text-rose-800">
          Gated to FAIL by <strong>{gatedBy.replace(/_/g, ' ')}</strong> (a CRITICAL gate).
        </div>
      )}
      {rubric.map((group, gi) => (
        <div key={gi}>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            Requirement: {group.requirement}
          </div>
          <ul className="space-y-1">
            {group.checks.map((c) => (
              <li key={c.id} className="flex items-start gap-2 rounded-md border border-slate-100 px-2 py-1.5">
                {c.score === 1 ? (
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                ) : c.score === 0 ? (
                  <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />
                ) : (
                  <span className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full bg-slate-200" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-slate-700">{c.text}</span>
                    <StatusChip tone={TIER_TONE[c.tier] || 'neutral'} size="xs">{(c.tier || '').toUpperCase()}</StatusChip>
                    <span className="text-[10px] text-slate-400">{c.dimension.replace(/_/g, ' ')}</span>
                    {c.must_pass && <StatusChip tone="danger" size="xs">must-pass</StatusChip>}
                    {c.attack_success && <StatusChip tone="danger" size="xs">attack landed</StatusChip>}
                  </div>
                  {c.reason && <div className="mt-0.5 text-[11px] italic text-slate-400">{c.reason}</div>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
      {perDimension?.length > 0 && (
        <div className="border-t border-slate-100 pt-2">
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Per-dimension score</div>
          <div className="flex flex-wrap gap-1.5">
            {perDimension.map((d) => (
              <StatusChip key={d.dimension} tone={d.gating ? TIER_TONE.critical : 'neutral'} size="xs">
                {d.dimension.replace(/_/g, ' ')} {d.score.toFixed(2)}{d.gating ? ' · gate' : ` · w${d.weight.toFixed(2)}`}
              </StatusChip>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function PointList({ label, tone, items }) {
  if (!items?.length) return null
  return (
    <div className="mb-2 last:mb-0">
      <div className="mb-1 flex items-center gap-1.5">
        <StatusChip tone={tone} size="xs">
          {label}
        </StatusChip>
      </div>
      <ul className="ml-1 list-inside list-disc space-y-0.5 text-xs text-slate-600">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  )
}
