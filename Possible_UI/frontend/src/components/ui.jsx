import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { X, Check, ChevronDown } from 'lucide-react'

// --- Toggle switch ---------------------------------------------------------
export function Toggle({ checked, onChange, label, description, disabled }) {
  return (
    <label className={`flex items-start gap-3 ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        className={`focusable relative mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-brand-600' : 'bg-slate-300'
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            checked ? 'translate-x-4' : 'translate-x-0.5'
          }`}
        />
      </button>
      {(label || description) && (
        <span className="leading-tight">
          {label && <span className="block text-sm font-medium text-slate-700">{label}</span>}
          {description && <span className="block text-xs text-slate-500">{description}</span>}
        </span>
      )}
    </label>
  )
}

// --- Labeled field wrapper -------------------------------------------------
export function Field({ label, hint, children, className = '' }) {
  return (
    <label className={`block ${className}`}>
      {label && <span className="mb-1.5 block text-xs font-semibold text-slate-600">{label}</span>}
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  )
}

const inputCls =
  'focusable w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 disabled:bg-slate-50'

export function Input(props) {
  return <input {...props} className={`${inputCls} ${props.className ?? ''}`} />
}
export function Textarea(props) {
  return <textarea {...props} className={`${inputCls} resize-y ${props.className ?? ''}`} />
}
export function Select({ children, ...props }) {
  return (
    <select {...props} className={`${inputCls} pr-8 ${props.className ?? ''}`}>
      {children}
    </select>
  )
}

// --- Checkbox --------------------------------------------------------------
export function Checkbox({ checked, onChange, label, disabled }) {
  return (
    <label className={`flex items-center gap-2.5 ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        className={`focusable flex h-4.5 w-4.5 items-center justify-center rounded border transition-colors ${
          checked ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white'
        }`}
        style={{ height: '1.125rem', width: '1.125rem' }}
      >
        {checked && <Check className="h-3 w-3" strokeWidth={3} />}
      </button>
      {label && <span className="text-sm text-slate-700">{label}</span>}
    </label>
  )
}

// --- Tabs ------------------------------------------------------------------
export function Tabs({ tabs, active, onChange, className = '' }) {
  return (
    <div className={`inline-flex items-center gap-1 rounded-lg bg-slate-100 p-1 ${className}`}>
      {tabs.map((t) => {
        const key = t.key ?? t
        const label = t.label ?? t
        const on = active === key
        return (
          <button
            key={key}
            type="button"
            onClick={() => onChange(key)}
            className={`focusable flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              on ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t.icon && <t.icon className="h-4 w-4" />}
            {label}
            {t.count != null && (
              <span className={`rounded-full px-1.5 text-[11px] ${on ? 'bg-brand-100 text-brand-700' : 'bg-slate-200 text-slate-500'}`}>
                {t.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// --- Empty state -----------------------------------------------------------
export function EmptyState({ icon: Icon, title, description, action, className = '' }) {
  return (
    <div className={`grid-backdrop flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50/50 px-6 py-12 text-center ${className}`}>
      {Icon && (
        <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-400 shadow-card">
          <Icon className="h-6 w-6" />
        </span>
      )}
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-xs text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

// --- Disclosure (collapsed "Advanced options") ----------------------------
// A bordered, collapsed-by-default section. When collapsed it shows a short
// summary of the values inside so nothing important is hidden — click to expand.
export function Disclosure({ title, summary, defaultOpen = false, icon: Icon, children, className = '' }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`overflow-hidden rounded-xl border border-slate-200 bg-white ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="focusable flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50"
      >
        {Icon && <Icon className="h-4 w-4 shrink-0 text-slate-400" />}
        <span className="shrink-0 text-sm font-semibold text-slate-700">{title}</span>
        {summary && !open && <span className="truncate text-xs text-slate-400">{summary}</span>}
        <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="border-t border-slate-100 px-4 py-4">{children}</div>}
    </div>
  )
}

// --- Progress bar ----------------------------------------------------------
export function ProgressBar({ value = 0, tone = 'brand', className = '' }) {
  const colors = {
    brand: 'bg-brand-600',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    danger: 'bg-rose-500',
  }
  return (
    <div className={`h-2 w-full overflow-hidden rounded-full bg-slate-200 ${className}`}>
      <div className={`h-full rounded-full transition-all ${colors[tone]}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  )
}

// --- Modal -----------------------------------------------------------------
export function Modal({ open, onClose, title, children, footer, size = 'md' }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  const widths = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-3xl' }
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-navy-900/40 backdrop-blur-sm" onClick={onClose} />
      <div className={`relative w-full ${widths[size]} animate-fade-in rounded-xl bg-white shadow-panel`}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="focusable rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3.5">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

// Tiny hook for copy-to-clipboard buttons.
export function useCopied(timeout = 1500) {
  const [copied, setCopied] = useState(false)
  const copy = (text) => {
    navigator.clipboard?.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), timeout)
  }
  return [copied, copy]
}
