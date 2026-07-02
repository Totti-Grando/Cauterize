import { useEffect, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  HelpCircle,
  Boxes,
  ScanSearch,
  FileStack,
  Quote,
  AlertTriangle,
  GitCompareArrows,
  Gauge,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ListChecks,
  Lightbulb,
  Cpu,
  Check,
  X,
} from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import { Card, CardHeader, CardBody } from '../components/Card'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import EvidenceCard from '../components/EvidenceCard'
import ExportButton from '../components/ExportButton'
import { api } from '../api'
import { verdictTone, verdictLabel, groundedTone, groundedLabel, supportTone, supportLabel } from '../lib/tone'

const TIER_TONE = { critical: 'danger', major: 'warning', minor: 'neutral' }

const TAGS = [
  { key: 'strong', label: 'Strong support' },
  { key: 'partial', label: 'Partial support' },
  { key: 'weak', label: 'Weak support' },
  { key: 'unsupported', label: 'Unsupported' },
  { key: 'not_evaluable', label: 'Not evaluable' },
]

export default function EvidenceDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { state } = useLocation()
  const passed = state?.evaluation          // the exact evaluation from the chat turn (with lessons)
  const lessons = state?.lessons || []
  const [rows, setRows] = useState([])

  useEffect(() => {
    if (!passed) api.getEvaluations().then(setRows)
  }, [passed])

  const idx = Math.max(0, rows.findIndex((x) => x.id === id))
  const e = passed ?? rows[idx] ?? rows[0]

  if (!e) {
    return (
      <PageContainer>
        <div className="h-64 animate-pulse rounded-xl bg-slate-200/60" />
      </PageContainer>
    )
  }

  const supportCount = (k) => e.evidence.filter((ev) => ev.support === k).length

  return (
    <PageContainer>
      <PageHeader
        title="Evidence Detail"
        description={`Full evidence review for ${e.questionId} — ${e.provider}`}
        actions={
          <>
            <Button variant="ghost" icon={ArrowLeft} onClick={() => navigate('/results')}>
              Back to results
            </Button>
            <Button
              variant="secondary"
              icon={ChevronLeft}
              disabled={idx <= 0}
              onClick={() => navigate(`/evidence/${rows[idx - 1].id}`)}
            >
              Prev
            </Button>
            <Button
              variant="secondary"
              iconRight={ChevronRight}
              disabled={idx >= rows.length - 1}
              onClick={() => navigate(`/evidence/${rows[idx + 1].id}`)}
            >
              Next
            </Button>
            <ExportButton size="md" label="Export" runId={e.id} />
          </>
        }
      />

      {/* Verdict banner */}
      <Card className="mb-6 flex flex-wrap items-center gap-3 px-5 py-4">
        <StatusChip tone={verdictTone(e.verdict)} dot>
          {verdictLabel(e.verdict)}
        </StatusChip>
        <StatusChip tone={groundedTone(e.sourceGroundedness)}>Source: {groundedLabel(e.sourceGroundedness)}</StatusChip>
        <StatusChip tone={e.grounded ? 'success' : 'danger'}>Grounded: {String(e.grounded)}</StatusChip>
        <span className="text-xs text-slate-400">Reasoning: {e.reasoningQuality}</span>
        <div className="ml-auto flex flex-wrap gap-1.5">
          {TAGS.map((t) => {
            const n = supportCount(t.key)
            return (
              <StatusChip key={t.key} tone={n ? supportTone(t.key) : 'neutral'} size="xs">
                {t.label}: {n}
              </StatusChip>
            )
          })}
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Question" icon={HelpCircle} />
            <CardBody className="text-sm text-slate-700">{e.question}</CardBody>
          </Card>
          <Card>
            <CardHeader title="Secondary provider answer" icon={Boxes} actions={<StatusChip tone="neutral" size="xs">{e.provider}</StatusChip>} />
            <CardBody className="text-sm leading-relaxed text-slate-700">{e.providerAnswer}</CardBody>
          </Card>
          <Card>
            <CardHeader title="Evaluator final summary" icon={ScanSearch} />
            <CardBody>
              <p className="rounded-lg bg-violet-50/60 px-3 py-2.5 text-sm text-violet-900">{e.finalSummary}</p>
            </CardBody>
          </Card>

          {e.rubric?.length > 0 && (
            <Card>
              <CardHeader
                title="Rubric & violations"
                subtitle="What was evaluated — each requirement's atomic checks, with failures flagged"
                icon={ListChecks}
                actions={e.gatedBy && <StatusChip tone="danger" size="xs">gated by {e.gatedBy.replace(/_/g, ' ')}</StatusChip>}
              />
              <CardBody className="space-y-4">
                {e.rubric.map((group, gi) => (
                  <div key={gi}>
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      {group.requirement}
                    </div>
                    <ul className="space-y-1.5">
                      {group.checks.map((c) => (
                        <li key={c.id} className={`flex items-start gap-2 rounded-md border px-2.5 py-1.5 ${c.score === 0 ? 'border-rose-200 bg-rose-50/50' : 'border-slate-100'}`}>
                          {c.score === 1 ? <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                            : c.score === 0 ? <X className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
                            : <span className="mt-0.5 h-4 w-4 shrink-0 rounded-full bg-slate-200" />}
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-sm text-slate-700">{c.text}</span>
                              <StatusChip tone={TIER_TONE[c.tier] || 'neutral'} size="xs">{(c.tier || '').toUpperCase()}</StatusChip>
                              <span className="text-[10px] text-slate-400">{c.dimension.replace(/_/g, ' ')}</span>
                              {c.must_pass && <StatusChip tone="danger" size="xs">must-pass</StatusChip>}
                              {c.attack_success && <StatusChip tone="danger" size="xs">attack landed</StatusChip>}
                            </div>
                            {c.reason && <div className="mt-0.5 text-xs italic text-slate-400">{c.reason}</div>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
                {e.perDimension?.length > 0 && (
                  <div className="border-t border-slate-100 pt-3">
                    <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Per-dimension score</div>
                    <div className="flex flex-wrap gap-1.5">
                      {e.perDimension.map((d) => (
                        <StatusChip key={d.dimension} tone={d.gating ? 'danger' : 'neutral'} size="xs">
                          {d.dimension.replace(/_/g, ' ')} {d.score.toFixed(2)}{d.gating ? ' · gate' : ` · w${d.weight.toFixed(2)}`}
                        </StatusChip>
                      ))}
                    </div>
                  </div>
                )}
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader
              title="Source chunks & extracted documents"
              subtitle={`${e.evidence.length} sources · RavenPack / link extraction`}
              icon={FileStack}
            />
            <CardBody className="space-y-3">
              {e.evidence.length ? (
                e.evidence.map((ev, i) => <EvidenceCard key={ev.id} evidence={ev} defaultOpen={i === 0} />)
              ) : (
                <div className="rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-400">
                  No source chunks were captured for this answer.
                </div>
              )}
            </CardBody>
          </Card>
        </div>

        {/* Right column — findings */}
        <div className="space-y-6">
          <Card>
            <CardHeader title="Evaluator details" icon={Cpu} />
            <CardBody className="space-y-2 text-xs text-slate-600">
              <Row label="Verdict" value={<StatusChip tone={verdictTone(e.verdict)} size="xs" dot>{verdictLabel(e.verdict)}</StatusChip>} />
              {typeof e.overall === 'number' && <Row label="Overall" value={<span className="font-medium text-slate-700">{e.overall.toFixed(2)}{e.failed ? ' (FAIL)' : ''}</span>} />}
              {e.gatedBy && <Row label="Gated by" value={<StatusChip tone="danger" size="xs">{e.gatedBy.replace(/_/g, ' ')}</StatusChip>} />}
              <Row label="Reasoning" value={<span className="text-slate-700">{e.reasoningQuality}</span>} />
              {e.evaluatorAgent?.model && <Row label="Judged by" value={<span className="font-mono text-[11px] text-slate-700">{e.evaluatorAgent.model}</span>} />}
              {e.providerAgent?.model && <Row label="Provider" value={<span className="font-mono text-[11px] text-slate-700">{e.providerAgent.model}</span>} />}
              {e.sameFamilyJudge && <Row label="Bias flag" value={<StatusChip tone="warning" size="xs">same-family judge</StatusChip>} />}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Lessons in play"
              subtitle="Deduped lessons applied to the next turn"
              icon={Lightbulb}
              actions={<StatusChip tone="neutral" size="xs">{lessons.length}</StatusChip>}
            />
            <CardBody>
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
                <span className="text-sm text-slate-400">No lessons yet — they appear after the first evaluated turn.</span>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Supporting quote" icon={Quote} />
            <CardBody>
              {e.evidence.find((ev) => ev.quote) ? (
                <blockquote className="border-l-2 border-brand-400 pl-3 text-sm italic text-slate-600">
                  “{e.evidence.find((ev) => ev.quote).quote}”
                </blockquote>
              ) : (
                <span className="text-sm text-slate-400">No supporting quote available.</span>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Unsupported claims" icon={AlertTriangle} />
            <CardBody>
              <FindingList items={e.incorrectPoints} tone="danger" empty="No unsupported claims flagged." />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Contradictions" icon={GitCompareArrows} />
            <CardBody>
              <FindingList
                items={e.shortfalls.includes('contradiction') ? ['Conflicting sentiment signals not reconciled.'] : []}
                tone="warning"
                empty="No contradictions detected."
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Source quality notes" icon={Gauge} />
            <CardBody className="space-y-2 text-xs text-slate-600">
              <div className="flex items-center justify-between">
                <span>Usable sources</span>
                <StatusChip tone="success" size="xs">
                  {e.evidence.filter((ev) => ev.fetchSuccess).length}
                </StatusChip>
              </div>
              <div className="flex items-center justify-between">
                <span>Login / blocked</span>
                <StatusChip tone="warning" size="xs">
                  {e.evidence.filter((ev) => !ev.fetchSuccess).length}
                </StatusChip>
              </div>
              <div className="flex items-center justify-between">
                <span>Total extracted text</span>
                <span className="font-medium text-slate-700">
                  {e.evidence.reduce((a, ev) => a + ev.textLength, 0).toLocaleString()} chars
                </span>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    </PageContainer>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-slate-400">{label}</span>
      {value}
    </div>
  )
}

function FindingList({ items, tone, empty }) {
  if (!items?.length) return <span className="text-sm text-slate-400">{empty}</span>
  return (
    <ul className="space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
          <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${tone === 'danger' ? 'bg-rose-500' : 'bg-amber-500'}`} />
          {it}
        </li>
      ))}
    </ul>
  )
}
