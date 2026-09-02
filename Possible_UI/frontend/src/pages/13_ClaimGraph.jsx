import { useEffect, useMemo, useState } from 'react'
import { Waypoints, ExternalLink, RefreshCw, AlertTriangle, ShieldAlert, GitFork } from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import { api } from '../api'

function Stat({ label, value, tone = 'slate' }) {
  const tones = { slate: 'text-slate-900', red: 'text-red-600', amber: 'text-amber-600', emerald: 'text-emerald-600' }
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-0.5 text-2xl font-bold ${tones[tone] || tones.slate}`}>{value}</div>
    </div>
  )
}

const RUBRIC_LEGEND = [
  { c: '#3b82f6', t: 'question' }, { c: '#8b5cf6', t: 'requirement' }, { c: '#0ea5e9', t: 'claim' },
  { c: '#64748b', t: 'check' }, { c: '#10b981', t: 'source' }, { c: '#f59e0b', t: 'dimension' },
]
const TREE_LEGEND = [
  { c: '#22c55e', t: 'green ≥75%' }, { c: '#eab308', t: 'amber ≥50%' }, { c: '#ef4444', t: 'red <50%' }, { c: '#64748b', t: 'abstain' },
]

export default function ClaimGraph() {
  const [view, setView] = useState('rubric') // 'rubric' | 'tree'
  const [runId, setRunId] = useState('')
  const [runs, setRuns] = useState([])
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    api.getRunHistory().then((rows) => setRuns(Array.isArray(rows) ? rows : [])).catch(() => {})
  }, [])

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    const p = view === 'tree' ? api.getClaimTree() : api.getGraph(runId || undefined)
    p.then((g) => alive && setData(g))
      .catch((e) => alive && setError(e.message || String(e)))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [view, runId, nonce])

  const isTree = view === 'tree'
  const s = data?.summary || data?.stats || {}
  const iframeUrl = useMemo(() => {
    const base = isTree ? api.claimTreeHtmlUrl() : api.graphHtmlUrl(runId || undefined)
    return `${base}${base.includes('?') ? '&' : '?'}v=${nonce}`
  }, [isTree, runId, nonce])

  const toggle = (
    <div className="inline-flex overflow-hidden rounded-lg border border-slate-300">
      {[['rubric', 'Rubric graph', Waypoints], ['tree', 'Claim tree (scored)', GitFork]].map(([k, label, Icon]) => (
        <button
          key={k}
          onClick={() => setView(k)}
          className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium ${
            view === k ? 'bg-brand-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Icon className="h-4 w-4" /> {label}
        </button>
      ))}
    </div>
  )

  return (
    <PageContainer>
      <PageHeader
        title="Claim Graph"
        description={
          isTree
            ? 'Per-claim truthfulness scoring. Anchored claims score min(groundedness, attribution, quality); derived claims are axiom-gated — max(own, reasoning) when load-bearing premises clear 75%, else min. Click a node for the full breakdown.'
            : 'Every claim and check as a node, wired to its requirement, dimension, and grounding source. Orphans and AND-gates (must-pass checks that can veto the run) are called out explicitly.'
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {toggle}
            {!isTree && (
              <select
                value={runId}
                onChange={(e) => setRunId(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
              >
                <option value="">Current evaluations</option>
                {runs.map((r) => (
                  <option key={r.runId} value={r.runId}>{r.runId} · {r.mode}</option>
                ))}
              </select>
            )}
            <button
              onClick={() => setNonce((n) => n + 1)}
              className="focusable inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCw className="h-4 w-4" /> Refresh
            </button>
            <a
              href={isTree ? api.claimTreeHtmlUrl() : api.graphHtmlUrl(runId || undefined)}
              target="_blank"
              rel="noreferrer"
              className="focusable inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              <ExternalLink className="h-4 w-4" /> Open standalone
            </a>
          </div>
        }
      />

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>Could not load the graph: {error}. Make sure the backend is running on :8000.</div>
        </div>
      )}

      {/* summary strip */}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {isTree ? (
          <>
            <Stat label="Nodes" value={loading ? '—' : s.nodes ?? 0} />
            <Stat label="Anchored" value={loading ? '—' : s.anchored ?? 0} />
            <Stat label="Derived" value={loading ? '—' : s.derived ?? 0} />
            <Stat label="Green" value={loading ? '—' : s.bands?.green ?? 0} tone="emerald" />
            <Stat label="Amber" value={loading ? '—' : s.bands?.amber ?? 0} tone="amber" />
            <Stat label="Red" value={loading ? '—' : s.bands?.red ?? 0} tone="red" />
          </>
        ) : (
          <>
            <Stat label="Evaluations" value={loading ? '—' : s.evaluations ?? 0} />
            <Stat label="Nodes" value={loading ? '—' : s.nodes ?? 0} />
            <Stat label="Edges" value={loading ? '—' : s.edges ?? 0} />
            <Stat label="Claims" value={loading ? '—' : (data?.graphs || []).reduce((a, g) => a + (g.stats?.claims || 0), 0)} tone="emerald" />
            <Stat label="Orphans" value={loading ? '—' : s.orphans ?? 0} tone={s.orphans ? 'red' : 'slate'} />
            <Stat label="AND-gates" value={loading ? '—' : s.gates ?? 0} tone={s.gates ? 'amber' : 'slate'} />
          </>
        )}
      </div>

      {/* legend */}
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
        {(isTree ? TREE_LEGEND : RUBRIC_LEGEND).map((l) => (
          <span key={l.t} className="inline-flex items-center gap-1.5">
            <span className="h-3 w-4 rounded" style={{ background: l.c }} />
            {l.t}
          </span>
        ))}
        {isTree ? (
          <>
            <span className="inline-flex items-center gap-1.5"><span className="h-0 w-4 border-t-2 border-slate-400" /> AND (load-bearing)</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-0 w-4 border-t-2 border-dashed border-slate-400" /> OR (alternative)</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-3 w-4 rounded border-2 border-dashed border-red-500" /> orphan</span>
          </>
        ) : (
          <>
            <span className="inline-flex items-center gap-1.5"><span className="h-3 w-4 rounded border-2 border-dashed border-red-500" /><AlertTriangle className="h-3.5 w-3.5 text-red-500" /> orphan</span>
            <span className="inline-flex items-center gap-1.5"><span className="h-3 w-4 rounded border-2 border-amber-500" /><ShieldAlert className="h-3.5 w-3.5 text-amber-500" /> gate</span>
          </>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {!isTree && s.evaluations === 0 && !loading ? (
          <div className="flex h-[70vh] items-center justify-center text-sm text-slate-400">
            No evaluations to graph yet — run an evaluation first.
          </div>
        ) : (
          <iframe key={iframeUrl} title="Claim graph canvas" src={iframeUrl} className="h-[72vh] w-full border-0" />
        )}
      </div>
    </PageContainer>
  )
}
