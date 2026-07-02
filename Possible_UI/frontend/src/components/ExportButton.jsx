import { useState } from 'react'
import { Download, FileJson, FileSpreadsheet, Check, Loader2, ChevronDown } from 'lucide-react'
import { api } from '../api'

// Export control with a small menu (CSV / JSON) and success state.
export default function ExportButton({ runId = 'current', label = 'Export', size = 'md', variant = 'secondary' }) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState('idle') // idle | working | done

  const run = async (kind) => {
    setOpen(false)
    setState('working')
    await api.exportCsv(runId)
    // (kind would select the format against the real backend)
    void kind
    setState('done')
    setTimeout(() => setState('idle'), 1800)
  }

  const sizeCls = size === 'sm' ? 'h-8 px-3 text-xs gap-1.5' : 'h-10 px-4 text-sm gap-2'
  const variantCls =
    variant === 'primary'
      ? 'bg-brand-600 text-white hover:bg-brand-700'
      : 'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50'

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={state === 'working'}
        className={`focusable inline-flex items-center rounded-lg font-semibold transition-colors ${sizeCls} ${variantCls} disabled:opacity-60`}
      >
        {state === 'working' ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : state === 'done' ? (
          <Check className="h-4 w-4 text-emerald-600" />
        ) : (
          <Download className="h-4 w-4" />
        )}
        {state === 'done' ? 'Exported' : label}
        <ChevronDown className="h-3.5 w-3.5 opacity-60" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-30 mt-1 w-48 animate-fade-in overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-panel">
            <button
              onClick={() => run('csv')}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              <FileSpreadsheet className="h-4 w-4 text-emerald-600" /> Export as CSV
            </button>
            <button
              onClick={() => run('json')}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              <FileJson className="h-4 w-4 text-brand-600" /> Export as JSON
            </button>
          </div>
        </>
      )}
    </div>
  )
}
