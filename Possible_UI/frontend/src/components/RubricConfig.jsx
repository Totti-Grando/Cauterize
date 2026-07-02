import { Scale, ShieldAlert, Wrench, Route, Bot } from 'lucide-react'
import StatusChip from './StatusChip'
import { Disclosure } from './ui'

// Read-only view of the evaluation rubric / config served by GET /api/rubric.
// This is the engine's source of truth — dimensions, tiers, gates, weighting, scorers, routing.

const TIER_TONE = { critical: 'danger', major: 'warning', minor: 'neutral' }
const TIER_ORDER = { critical: 0, major: 1, minor: 2 }

export default function RubricConfig({ data }) {
  if (!data) {
    return <div className="h-40 animate-pulse rounded-xl bg-slate-200/60" />
  }
  const { weighting, tiers = [], dimensions = [], scorers = [], routing = [] } = data
  const groups = tiers
    .slice()
    .sort((a, b) => (TIER_ORDER[a.tier] ?? 9) - (TIER_ORDER[b.tier] ?? 9))
    .map((t) => ({ ...t, dims: dimensions.filter((d) => d.tier === t.tier) }))

  return (
    <div className="space-y-4">
      {/* Weighting & gating — how a verdict becomes a score */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-slate-700">
          <Scale className="h-4 w-4 text-slate-400" /> Scoring & gating
        </div>
        <div className="mb-3 flex flex-wrap gap-1.5">
          <StatusChip tone="neutral" size="xs">MAJOR : MINOR = {weighting?.major_minor_ratio}× : 1×</StatusChip>
          <StatusChip tone="neutral" size="xs">gating min runs: {weighting?.gating_min_runs}</StatusChip>
          <StatusChip tone="neutral" size="xs">config {weighting?.config_version}</StatusChip>
        </div>
        <dl className="space-y-2 text-xs leading-relaxed text-slate-600">
          <div>
            <dt className="font-semibold text-slate-500">Overall score</dt>
            <dd>{weighting?.overall_formula}</dd>
          </div>
          <div>
            <dt className="font-semibold text-slate-500">Gate rule</dt>
            <dd>{weighting?.gate_rule}</dd>
          </div>
        </dl>
      </div>

      {/* Dimensions grouped by tier */}
      {groups.map((g) => (
        <div key={g.tier} className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="mb-1 flex items-center gap-2">
            {g.tier === 'critical' && <ShieldAlert className="h-4 w-4 text-rose-500" />}
            <span className="text-sm font-semibold text-slate-800">{g.label} dimensions</span>
            <StatusChip tone={TIER_TONE[g.tier]} size="xs">
              {g.tier === 'critical' ? 'gating' : `weight ${g.weight}×`}
            </StatusChip>
            <span className="ml-auto text-xs text-slate-400">{g.dims.length}</span>
          </div>
          <p className="mb-3 text-xs text-slate-500">{g.description}</p>
          <ul className="space-y-1.5">
            {g.dims.map((d) => (
              <li key={d.id} className="rounded-lg border border-slate-100 px-3 py-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium text-slate-700">{d.label}</span>
                  <span className="font-mono text-[10px] text-slate-400">{d.id}</span>
                  {d.gating ? (
                    <StatusChip tone="danger" size="xs">gate ≥ {d.gate_threshold}</StatusChip>
                  ) : (
                    <StatusChip tone="neutral" size="xs">weight {d.weight}×</StatusChip>
                  )}
                  {d.owasp && <StatusChip tone="warning" size="xs">{d.owasp}</StatusChip>}
                  {d.agentic_only && (
                    <StatusChip tone="info" size="xs">
                      <Bot className="mr-0.5 h-3 w-3" /> agentic only
                    </StatusChip>
                  )}
                </div>
                {d.description && <div className="mt-0.5 text-xs text-slate-500">{d.description}</div>}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {/* Scorers + routing — collapsed, for the curious */}
      <Disclosure
        icon={Wrench}
        title="Scorers & routing"
        summary={`${scorers.length} scorers · how each check is graded`}
      >
        <div className="space-y-4">
          <ul className="space-y-1.5">
            {scorers.map((s) => (
              <li key={s.id} className="rounded-lg border border-slate-100 px-3 py-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-slate-700">{s.label}</span>
                  <span className="font-mono text-[10px] text-slate-400">{s.id}</span>
                </div>
                <div className="mt-0.5 text-xs text-slate-500">{s.description}</div>
              </li>
            ))}
          </ul>
          <div>
            <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-slate-600">
              <Route className="h-3.5 w-3.5 text-slate-400" /> How a check is routed to a scorer
            </div>
            <ol className="list-inside list-decimal space-y-1 text-xs text-slate-600">
              {routing.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ol>
          </div>
        </div>
      </Disclosure>
    </div>
  )
}
