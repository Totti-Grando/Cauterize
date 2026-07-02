import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  History,
  Copy,
  FileSpreadsheet,
  FileJson,
  Trash2,
  ArrowRight,
  ChevronDown,
  FileText,
  Link2,
  Cpu,
  Boxes,
  GitBranch,
  StickyNote,
} from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import { Card } from '../components/Card'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import { Tabs } from '../components/ui'
import { api } from '../api'

const EXPORT_TONE = { exported: 'success', pending: 'warning', draft: 'neutral' }
const MODE_TONE = { Assisted: 'brand', Automatic: 'info', Manual: 'neutral' }

export default function RunHistory() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    api.getRunHistory().then((d) => {
      setRuns(d)
      setLoading(false)
    })
  }, [])

  const filtered = runs.filter((r) => filter === 'all' || r.exportStatus === filter)

  return (
    <PageContainer>
      <PageHeader
        title="Run History & Audit Trail"
        description="Every run with its configuration, sources, and outputs — retained for audit."
        actions={
          <Tabs
            active={filter}
            onChange={setFilter}
            tabs={[
              { key: 'all', label: 'All' },
              { key: 'exported', label: 'Exported' },
              { key: 'pending', label: 'Pending' },
              { key: 'draft', label: 'Drafts' },
            ]}
          />
        }
      />

      {/* Table */}
      <Card className="mb-6 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3 font-semibold">Run ID</th>
                <th className="px-4 py-3 font-semibold">Date</th>
                <th className="px-4 py-3 font-semibold">User</th>
                <th className="px-4 py-3 font-semibold">Docs</th>
                <th className="px-4 py-3 font-semibold">Links</th>
                <th className="px-4 py-3 font-semibold">Primary</th>
                <th className="px-4 py-3 font-semibold">Provider</th>
                <th className="px-4 py-3 font-semibold">Mode</th>
                <th className="px-4 py-3 font-semibold">Qs</th>
                <th className="px-4 py-3 font-semibold">Verdicts</th>
                <th className="px-4 py-3 font-semibold">Export</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={12} className="px-4 py-10 text-center text-slate-400">
                    Loading run history…
                  </td>
                </tr>
              ) : (
                filtered.map((r) => (
                  <tr key={r.runId} className="hover:bg-slate-50/70">
                    <td className="px-4 py-3 font-mono text-xs font-semibold text-brand-700">{r.runId}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{r.date}</td>
                    <td className="px-4 py-3 text-slate-600">{r.user}</td>
                    <td className="px-4 py-3 tabular-nums text-slate-600">{r.documents}</td>
                    <td className="px-4 py-3 tabular-nums text-slate-600">{r.links}</td>
                    <td className="px-4 py-3 text-slate-600">{r.primaryModel}</td>
                    <td className="px-4 py-3 text-slate-600">{r.provider}</td>
                    <td className="px-4 py-3">
                      <StatusChip tone={MODE_TONE[r.mode]} size="xs">
                        {r.mode}
                      </StatusChip>
                    </td>
                    <td className="px-4 py-3 tabular-nums text-slate-600">{r.questions}</td>
                    <td className="px-4 py-3">
                      <VerdictMini v={r.verdictSummary} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusChip tone={EXPORT_TONE[r.exportStatus]} size="xs" dot>
                        {r.exportStatus}
                      </StatusChip>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setExpanded(expanded === r.runId ? null : r.runId)}
                        className="focusable rounded-md p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                      >
                        <ChevronDown className={`h-4 w-4 transition-transform ${expanded === r.runId ? 'rotate-180' : ''}`} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Run cards (configuration snapshots) */}
      <div className="space-y-4">
        {filtered.map((r) => (
          <Card key={r.runId} className={`overflow-hidden ${expanded && expanded !== r.runId ? 'hidden' : ''}`}>
            <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 bg-slate-50 px-5 py-3">
              <span className="font-mono text-sm font-semibold text-slate-900">{r.runId}</span>
              <StatusChip tone={MODE_TONE[r.mode]} size="xs">
                {r.mode}
              </StatusChip>
              <span className="text-xs text-slate-400">{r.date}</span>
              <div className="ml-auto flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" icon={Copy}>
                  Duplicate
                </Button>
                <Button size="sm" variant="secondary" icon={FileSpreadsheet}>
                  Export CSV
                </Button>
                <Button size="sm" variant="secondary" icon={FileJson}>
                  Export JSON
                </Button>
                <Button size="sm" variant="ghost" icon={Trash2}>
                  Delete draft
                </Button>
                <Button size="sm" icon={ArrowRight} onClick={() => navigate('/results')}>
                  Open run
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-5 px-5 py-4 md:grid-cols-2 lg:grid-cols-4">
              <Snapshot
                title="Configuration"
                items={[
                  { icon: Cpu, label: 'Primary model', value: r.primaryModel },
                  { icon: Boxes, label: 'Secondary provider', value: r.provider },
                  { icon: GitBranch, label: 'Q&A mode', value: r.mode },
                ]}
              />
              <Snapshot
                title="Sources"
                items={[
                  { icon: FileText, label: 'Documents', value: r.documents },
                  { icon: Link2, label: 'Links', value: r.links },
                ]}
              />
              <Snapshot
                title="Evaluation settings"
                items={[
                  { icon: GitBranch, label: 'Questions', value: r.questions },
                  { icon: Boxes, label: 'Output files', value: r.exportStatus === 'exported' ? 'CSV, JSON' : '—' },
                ]}
              />
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  <StickyNote className="h-3.5 w-3.5" /> Notes
                </div>
                <p className="text-xs leading-relaxed text-slate-600">{r.notes}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </PageContainer>
  )
}

function VerdictMini({ v }) {
  const items = [
    { n: v.correct, tone: 'success' },
    { n: v.partial, tone: 'warning' },
    { n: v.incorrect, tone: 'danger' },
    { n: v.unverifiable, tone: 'info' },
  ]
  return (
    <div className="flex gap-1">
      {items.map((it, i) => (
        <StatusChip key={i} tone={it.tone} size="xs">
          {it.n}
        </StatusChip>
      ))}
    </div>
  )
}

function Snapshot({ title, items }) {
  return (
    <div>
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{title}</div>
      <dl className="space-y-1.5">
        {items.map((it) => (
          <div key={it.label} className="flex items-center justify-between text-xs">
            <dt className="flex items-center gap-1.5 text-slate-400">
              <it.icon className="h-3 w-3" /> {it.label}
            </dt>
            <dd className="font-medium text-slate-700">{it.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
