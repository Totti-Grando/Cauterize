import { Link2, FileSearch, ArrowRight, X } from 'lucide-react'
import SelectableCard from './SelectableCard'
import StatusChip from './StatusChip'

const ACCENT = {
  brand: 'bg-brand-50 text-brand-700',
  violet: 'bg-violet-50 text-violet-700',
  slate: 'bg-slate-100 text-slate-600',
}

// Secondary-provider card (RavenPack / Nexa / Custom).
// `configured` (bool | null): null hides the status chip; true/false shows configured/setup state.
export default function ProviderCard({ provider, selected, onSelect, configured = null }) {
  return (
    <SelectableCard selected={selected} onSelect={onSelect}>
      <div className="mb-3 flex items-center gap-3">
        <span className={`flex h-10 w-10 items-center justify-center rounded-lg text-sm font-bold ${ACCENT[provider.accent] ?? ACCENT.slate}`}>
          {provider.name.slice(0, 2)}
        </span>
        <div className="flex-1">
          <div className="text-sm font-semibold text-slate-900">{provider.name}</div>
          <div className="text-[11px] text-slate-400">Secondary provider</div>
        </div>
        {configured !== null && (
          <StatusChip tone={configured ? 'success' : 'warning'} size="xs" dot>
            {configured ? 'Configured' : 'Setup required'}
          </StatusChip>
        )}
      </div>
      <p className="mb-3 min-h-[40px] text-xs leading-relaxed text-slate-500">{provider.description}</p>
      <dl className="space-y-1.5 text-xs">
        <div className="flex items-center justify-between">
          <dt className="text-slate-400">Output type</dt>
          <dd className="font-medium text-slate-600">{provider.outputType}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1 text-slate-400">
            <Link2 className="h-3 w-3" /> Link support
          </dt>
          <dd>{provider.linkSupport ? <Yes /> : <No />}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1 text-slate-400">
            <FileSearch className="h-3 w-3" /> Evidence support
          </dt>
          <dd>{provider.evidenceSupport ? <Yes /> : <No />}</dd>
        </div>
      </dl>
    </SelectableCard>
  )
}

const Yes = () => (
  <StatusChip tone="success" size="xs">
    Yes
  </StatusChip>
)
const No = () => (
  <StatusChip tone="neutral" size="xs">
    <X className="h-3 w-3" /> No
  </StatusChip>
)
