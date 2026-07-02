import { Check } from 'lucide-react'

// Generic selectable tile used by ModelCard / ProviderCard / ModeCard.
export default function SelectableCard({ selected, onSelect, children, className = '', disabled }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onSelect?.()}
      disabled={disabled}
      className={`focusable group relative w-full rounded-xl border bg-white p-5 text-left shadow-card transition-all disabled:opacity-50 ${
        selected
          ? 'border-brand-500 ring-2 ring-brand-200'
          : 'border-slate-200 hover:border-brand-300 hover:shadow-cardhover'
      } ${className}`}
    >
      {selected && (
        <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-brand-600 text-white shadow-sm">
          <Check className="h-3.5 w-3.5" strokeWidth={3} />
        </span>
      )}
      {children}
    </button>
  )
}
