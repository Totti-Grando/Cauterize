import { useNavigate } from 'react-router-dom'
import { Eye, FileSearch, Copy, Download, Check } from 'lucide-react'
import StatusChip from './StatusChip'
import { verdictTone, verdictLabel, groundedTone, groundedLabel, shortfallTone, prettyTag } from '../lib/tone'
import { useCopied } from './ui'

// Auditable results table used on the Results Dashboard.
export default function ResultsTable({ rows }) {
  const navigate = useNavigate()
  const [copied, copy] = useCopied()

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3 font-semibold">Question</th>
              <th className="px-4 py-3 font-semibold">Provider</th>
              <th className="px-4 py-3 font-semibold">Verdict</th>
              <th className="px-4 py-3 font-semibold">Grounded</th>
              <th className="px-4 py-3 font-semibold">Shortfalls</th>
              <th className="px-4 py-3 font-semibold">Source</th>
              <th className="px-4 py-3 font-semibold">Summary</th>
              <th className="px-4 py-3 text-center font-semibold">Evidence</th>
              <th className="px-4 py-3 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((e) => (
              <tr key={e.id} className="group align-top transition-colors hover:bg-slate-50/70">
                <td className="max-w-[260px] px-4 py-3">
                  <div className="line-clamp-2 font-medium text-slate-800">{e.question}</div>
                  <div className="mt-0.5 text-[11px] text-slate-400">{e.questionId}</div>
                </td>
                <td className="px-4 py-3 text-slate-600">{e.provider}</td>
                <td className="px-4 py-3">
                  <StatusChip tone={verdictTone(e.verdict)} dot>
                    {verdictLabel(e.verdict)}
                  </StatusChip>
                </td>
                <td className="px-4 py-3">
                  <StatusChip tone={e.grounded ? 'success' : 'danger'} size="xs">
                    {String(e.grounded)}
                  </StatusChip>
                </td>
                <td className="max-w-[180px] px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {e.shortfalls.length ? (
                      e.shortfalls.map((s) => (
                        <StatusChip key={s} tone={shortfallTone(s)} size="xs">
                          {prettyTag(s)}
                        </StatusChip>
                      ))
                    ) : (
                      <span className="text-xs text-slate-300">—</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <StatusChip tone={groundedTone(e.sourceGroundedness)} size="xs">
                    {groundedLabel(e.sourceGroundedness)}
                  </StatusChip>
                </td>
                <td className="max-w-[280px] px-4 py-3">
                  <div className="line-clamp-2 text-xs text-slate-500">{e.finalSummary}</div>
                </td>
                <td className="px-4 py-3 text-center tabular-nums text-slate-600">{e.evidence.length}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1 opacity-60 transition-opacity group-hover:opacity-100">
                    <IconBtn title="Open details" onClick={() => navigate(`/evidence/${e.id}`)} icon={Eye} />
                    <IconBtn title="View evidence" onClick={() => navigate(`/evidence/${e.id}`)} icon={FileSearch} />
                    <IconBtn
                      title="Copy JSON"
                      onClick={() => copy(JSON.stringify(e, null, 2))}
                      icon={copied ? Check : Copy}
                    />
                    <IconBtn title="Export row" onClick={() => {}} icon={Download} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function IconBtn({ title, onClick, icon: Icon }) {
  return (
    <button
      title={title}
      onClick={onClick}
      className="focusable rounded-md p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}
