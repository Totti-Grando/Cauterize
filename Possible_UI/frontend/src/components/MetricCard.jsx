import { Card } from './Card'

const TONE = {
  neutral: { ring: 'ring-slate-200', value: 'text-slate-900', accent: 'bg-slate-100 text-slate-500' },
  success: { ring: 'ring-emerald-200', value: 'text-emerald-700', accent: 'bg-emerald-50 text-emerald-600' },
  warning: { ring: 'ring-amber-200', value: 'text-amber-700', accent: 'bg-amber-50 text-amber-600' },
  danger: { ring: 'ring-rose-200', value: 'text-rose-700', accent: 'bg-rose-50 text-rose-600' },
  info: { ring: 'ring-sky-200', value: 'text-sky-700', accent: 'bg-sky-50 text-sky-600' },
  brand: { ring: 'ring-brand-200', value: 'text-brand-700', accent: 'bg-brand-50 text-brand-600' },
}

// Compact KPI card used on Results, Run Monitor, dashboards.
export default function MetricCard({ label, value, tone = 'neutral', icon: Icon, delta, hint }) {
  const t = TONE[tone] ?? TONE.neutral
  return (
    <Card className={`p-4 ring-1 ${t.ring}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-medium text-slate-500">{label}</div>
        {Icon && (
          <span className={`flex h-7 w-7 items-center justify-center rounded-md ${t.accent}`}>
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>
      <div className={`mt-2 text-2xl font-bold tabular-nums ${t.value}`}>{value}</div>
      {(delta || hint) && (
        <div className="mt-1 text-xs text-slate-400">
          {delta && <span className="font-medium text-slate-500">{delta}</span>} {hint}
        </div>
      )}
    </Card>
  )
}
