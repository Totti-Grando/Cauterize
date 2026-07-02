import { useEffect, useRef, useState } from 'react'
import { Info, X } from 'lucide-react'

/**
 * Chat-style layout shared by the manual / assisted / automatic mode pages.
 * A slim top bar (title + status + a corner "Run info" button), a centered transcript,
 * an optional composer pinned to the bottom, and a slide-over drawer for run details.
 *
 * Props:
 *   title, subtitle, statusChip, headerActions — top bar content
 *   runInfo    — node rendered inside the run-info drawer
 *   composer   — node pinned at the bottom (omit for read-only modes)
 *   scrollKey  — value that, when it changes, auto-scrolls the transcript to the bottom
 */
export default function ChatShell({ title, subtitle, statusChip, headerActions, runInfo, composer, scrollKey, children }) {
  const [info, setInfo] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [scrollKey])

  return (
    <div className="relative flex h-full flex-col overflow-hidden bg-slate-50">
      {/* Top bar */}
      <header className="z-10 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-bold text-slate-900">{title}</h1>
          {subtitle && <p className="truncate text-xs text-slate-400">{subtitle}</p>}
        </div>
        {statusChip}
        <div className="ml-auto flex items-center gap-2">
          {headerActions}
          <button
            onClick={() => setInfo((v) => !v)}
            title="Show run info"
            className={`focusable inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
              info ? 'border-brand-300 bg-brand-50 text-brand-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            <Info className="h-4 w-4" /> Run info
          </button>
        </div>
      </header>

      {/* Transcript */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6">{children}</div>
      </div>

      {/* Composer */}
      {composer && (
        <div className="border-t border-slate-200 bg-white px-4 py-3">
          <div className="mx-auto max-w-3xl">{composer}</div>
        </div>
      )}

      {/* Run-info drawer */}
      {info && (
        <>
          <div className="absolute inset-0 z-20 bg-navy-900/20" onClick={() => setInfo(false)} />
          <aside className="absolute right-0 top-0 z-30 flex h-full w-[380px] max-w-[92vw] animate-fade-in flex-col border-l border-slate-200 bg-white shadow-panel">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <span className="text-sm font-semibold text-slate-900">Run information</span>
              <button onClick={() => setInfo(false)} className="focusable rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">{runInfo}</div>
          </aside>
        </>
      )}
    </div>
  )
}
