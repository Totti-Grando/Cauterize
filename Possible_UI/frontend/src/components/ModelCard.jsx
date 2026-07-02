import { Cpu, Check } from 'lucide-react'
import StatusChip from './StatusChip'

// Selectable Bedrock model row (used as the rich dropdown body on Model setup).
export default function ModelCard({ model, selected, onSelect }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`focusable flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-all ${
        selected ? 'border-brand-500 bg-brand-50/60 ring-1 ring-brand-200' : 'border-slate-200 bg-white hover:border-brand-300'
      }`}
    >
      <span
        className={`flex h-9 w-9 items-center justify-center rounded-lg ${
          selected ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500'
        }`}
      >
        <Cpu className="h-4.5 w-4.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-800">{model.label}</span>
          <StatusChip tone="neutral" size="xs">
            {model.tier}
          </StatusChip>
        </div>
        <div className="truncate text-xs text-slate-400">{model.note}</div>
      </div>
      {selected && (
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-600 text-white">
          <Check className="h-3 w-3" strokeWidth={3} />
        </span>
      )}
    </button>
  )
}
