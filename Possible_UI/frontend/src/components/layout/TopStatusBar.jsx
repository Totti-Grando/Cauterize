import { FileText, Link2, Cpu, Boxes, GitBranch, CircleDot } from 'lucide-react'
import { useRun } from '../../context/RunContext'
import StatusChip from '../StatusChip'

const STATUS_TONE = {
  Draft: 'neutral',
  Configuring: 'info',
  Ready: 'brand',
  Running: 'warning',
  Paused: 'warning',
  Complete: 'success',
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="h-4 w-4 text-slate-400" />
      <span className="text-xs text-slate-400">{label}</span>
      <span className="text-xs font-semibold text-slate-700">{value}</span>
    </div>
  )
}

// Top bar describing the current evaluation run — always visible above content.
export default function TopStatusBar() {
  const { run, summary } = useRun()
  return (
    <header className="z-10 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-5 overflow-x-auto">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Current Run</span>
        <div className="h-4 w-px bg-slate-200" />
        <Stat icon={FileText} label="Docs" value={summary.documents} />
        <Stat icon={Link2} label="Links" value={summary.links} />
        <Stat icon={Cpu} label="Primary" value={summary.primaryModelLabel} />
        <Stat icon={Boxes} label="Provider" value={summary.providerLabel} />
        <Stat icon={GitBranch} label="Mode" value={summary.modeLabel} />
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="hidden items-center gap-1.5 text-xs text-slate-400 md:flex">
          <CircleDot className="h-3.5 w-3.5" /> Round {run.round}
        </span>
        <StatusChip tone={STATUS_TONE[run.status] ?? 'neutral'} dot pulse={run.status === 'Running'}>
          {run.status}
        </StatusChip>
      </div>
    </header>
  )
}
