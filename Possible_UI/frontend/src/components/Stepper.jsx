import { Check } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

// Horizontal evaluation-journey stepper: Sources -> Models -> Q&A Mode -> Run -> Review -> Export
export const JOURNEY_STEPS = [
  { key: 'sources', label: 'Sources', to: '/sources' },
  { key: 'models', label: 'Models', to: '/models' },
  { key: 'qa', label: 'Q&A Mode', to: '/qa-mode' },
  { key: 'run', label: 'Run', to: '/workspace' },
  { key: 'review', label: 'Review', to: '/results' },
  { key: 'export', label: 'Export', to: '/history' },
]

export default function Stepper({ current = 0, steps = JOURNEY_STEPS, clickable = true, className = '' }) {
  const navigate = useNavigate()
  return (
    <nav className={`flex items-center ${className}`} aria-label="Evaluation journey">
      {steps.map((step, i) => {
        const done = i < current
        const active = i === current
        const stateCls = done
          ? 'bg-emerald-500 text-white ring-emerald-500'
          : active
            ? 'bg-brand-600 text-white ring-brand-600 ring-4 ring-brand-100'
            : 'bg-white text-slate-400 ring-slate-300'
        return (
          <div key={step.key} className="flex items-center" style={{ flex: i === steps.length - 1 ? '0 0 auto' : '1 1 0%' }}>
            <button
              type="button"
              disabled={!clickable}
              onClick={() => clickable && step.to && navigate(step.to)}
              className="focusable group flex shrink-0 flex-col items-center gap-1.5 disabled:cursor-default"
            >
              <span
                className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ring-1 transition-all ${stateCls}`}
              >
                {done ? <Check className="h-4 w-4" /> : i + 1}
              </span>
              <span
                className={`text-xs font-semibold ${active ? 'text-brand-700' : done ? 'text-slate-600' : 'text-slate-400'}`}
              >
                {step.label}
              </span>
            </button>
            {i < steps.length - 1 && (
              <span className={`mx-2 h-0.5 flex-1 rounded-full ${done ? 'bg-emerald-400' : 'bg-slate-200'}`} />
            )}
          </div>
        )
      })}
    </nav>
  )
}
