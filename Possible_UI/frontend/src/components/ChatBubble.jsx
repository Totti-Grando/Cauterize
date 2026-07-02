import { User, Boxes, ScanSearch } from 'lucide-react'

// Chat bubbles for the evaluation workspace.
// role: 'question' (user) | 'answer' (secondary provider) | 'evaluator' (system card)
export default function ChatBubble({ role = 'question', author, time, children }) {
  if (role === 'question') {
    return (
      <div className="flex justify-end">
        <div className="flex max-w-[80%] items-start gap-3">
          <div className="rounded-2xl rounded-tr-sm bg-brand-600 px-4 py-3 text-sm text-white shadow-sm">
            {children}
            {time && <div className="mt-1 text-[11px] text-brand-100/80">{time}</div>}
          </div>
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
            <User className="h-4 w-4" />
          </span>
        </div>
      </div>
    )
  }

  if (role === 'answer') {
    return (
      <div className="flex justify-start">
        <div className="flex max-w-[85%] items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy-800 text-white">
            <Boxes className="h-4 w-4" />
          </span>
          <div className="rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">
            {author && <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{author}</div>}
            {children}
            {time && <div className="mt-1 text-[11px] text-slate-400">{time}</div>}
          </div>
        </div>
      </div>
    )
  }

  // evaluator
  return (
    <div className="flex justify-start pl-11">
      <div className="flex w-full items-start gap-2 rounded-lg border border-violet-200 bg-violet-50/60 px-3 py-2 text-xs text-violet-900">
        <ScanSearch className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-500" />
        <div>{children}</div>
      </div>
    </div>
  )
}
