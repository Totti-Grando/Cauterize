import { Check, Loader2, Circle, AlertTriangle } from 'lucide-react'

const STATE = {
  done: { icon: Check, ring: 'border-emerald-500 bg-emerald-500 text-white', line: 'bg-emerald-400', text: 'text-slate-700' },
  active: { icon: Loader2, ring: 'border-brand-500 bg-brand-50 text-brand-600', line: 'bg-slate-200', text: 'text-brand-700 font-semibold' },
  pending: { icon: Circle, ring: 'border-slate-300 bg-white text-slate-300', line: 'bg-slate-200', text: 'text-slate-400' },
  error: { icon: AlertTriangle, ring: 'border-rose-500 bg-rose-50 text-rose-600', line: 'bg-slate-200', text: 'text-rose-700' },
}

// Vertical pipeline timeline used by the Automatic Run Monitor.
export default function ProgressTimeline({ steps }) {
  return (
    <ol className="relative">
      {steps.map((s, i) => {
        const st = STATE[s.status] ?? STATE.pending
        const Icon = st.icon
        const last = i === steps.length - 1
        return (
          <li key={s.step} className="relative flex gap-4 pb-6 last:pb-0">
            {!last && <span className={`absolute left-[15px] top-8 h-[calc(100%-16px)] w-0.5 ${st.line}`} />}
            <span className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 ${st.ring}`}>
              <Icon className={`h-4 w-4 ${s.status === 'active' ? 'animate-spin' : ''}`} />
            </span>
            <div className="pt-1">
              <div className={`text-sm ${st.text}`}>{s.step}</div>
              {s.message && <div className="mt-0.5 text-xs text-slate-400">{s.message}</div>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
