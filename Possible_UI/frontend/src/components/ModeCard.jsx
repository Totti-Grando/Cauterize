import { PencilLine, Sparkles, Workflow, User, ThumbsUp, ThumbsDown, Loader2 } from 'lucide-react'
import SelectableCard from './SelectableCard'

const ICONS = { PencilLine, Sparkles, Workflow }

// Visual preview shown inside each Q&A-mode card.
function Preview({ id }) {
  if (id === 'manual') {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2.5">
        <User className="h-4 w-4 text-slate-400" />
        <div className="h-2 flex-1 rounded-full bg-slate-200">
          <div className="h-2 w-2/3 rounded-full bg-brand-400" />
        </div>
        <span className="text-[11px] text-slate-400">typing…</span>
      </div>
    )
  }
  if (id === 'assisted') {
    return (
      <div className="space-y-1.5 rounded-lg bg-slate-50 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-violet-500" />
          <div className="h-1.5 flex-1 rounded-full bg-slate-200" />
          <ThumbsUp className="h-3.5 w-3.5 text-emerald-500" />
          <ThumbsDown className="h-3.5 w-3.5 text-rose-400" />
        </div>
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-violet-500" />
          <div className="h-1.5 flex-1 rounded-full bg-slate-200" />
          <ThumbsUp className="h-3.5 w-3.5 text-slate-300" />
          <ThumbsDown className="h-3.5 w-3.5 text-slate-300" />
        </div>
      </div>
    )
  }
  return (
    <div className="space-y-1.5 rounded-lg bg-slate-50 px-3 py-2.5">
      <div className="flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-500" />
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200">
          <div className="h-full w-3/4 rounded-full bg-brand-500" />
        </div>
        <span className="text-[11px] tabular-nums text-slate-400">3/5</span>
      </div>
      <div className="flex gap-1">
        {['gen', 'query', 'eval', 'write'].map((s, i) => (
          <span key={s} className={`h-1 flex-1 rounded-full ${i < 2 ? 'bg-emerald-400' : 'bg-slate-200'}`} />
        ))}
      </div>
    </div>
  )
}

// Large Q&A-mode selection card.
export default function ModeCard({ mode, selected, onSelect }) {
  const Icon = ICONS[mode.icon] ?? PencilLine
  return (
    <SelectableCard selected={selected} onSelect={onSelect} className="flex flex-col">
      <div className="mb-3 flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
          <Icon className="h-5.5 w-5.5" />
        </span>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{mode.name}</div>
          <div className="text-base font-bold text-slate-900">{mode.title}</div>
        </div>
      </div>
      <p className="mb-4 flex-1 text-sm leading-relaxed text-slate-500">{mode.description}</p>
      <Preview id={mode.id} />
    </SelectableCard>
  )
}
