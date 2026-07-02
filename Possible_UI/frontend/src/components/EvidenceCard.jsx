import { useState } from 'react'
import { ChevronDown, Quote, Globe, ExternalLink, CalendarDays, User2, FileText, CheckCircle2, XCircle } from 'lucide-react'
import StatusChip from './StatusChip'
import { supportTone, supportLabel } from '../lib/tone'

// Expandable evidence source card for the Evidence Detail view.
export default function EvidenceCard({ evidence: ev, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
      <button
        onClick={() => setOpen((o) => !o)}
        className="focusable flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-slate-50"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
          <Globe className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-slate-800">{ev.title}</div>
          <div className="truncate text-xs text-slate-400">{ev.domain}</div>
        </div>
        <StatusChip tone={supportTone(ev.support)} size="xs">
          {supportLabel(ev.support)}
        </StatusChip>
        {ev.fetchSuccess ? (
          <StatusChip tone="success" size="xs" dot>
            Fetched
          </StatusChip>
        ) : (
          <StatusChip tone="warning" size="xs" dot>
            Login / blocked
          </StatusChip>
        )}
        <ChevronDown className={`h-4 w-4 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="border-t border-slate-100 px-4 py-4">
          {ev.quote ? (
            <blockquote className="mb-4 flex gap-2 rounded-lg border-l-2 border-brand-400 bg-brand-50/50 px-3 py-2 text-sm italic text-slate-700">
              <Quote className="h-4 w-4 shrink-0 text-brand-400" />
              {ev.quote}
            </blockquote>
          ) : (
            <div className="mb-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-400">
              No supporting quote — source could not be read.
            </div>
          )}

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-xs sm:grid-cols-3">
            <Meta icon={FileText} label="Title" value={ev.title} />
            <Meta icon={User2} label="Author" value={ev.author ?? '—'} />
            <Meta icon={CalendarDays} label="Published" value={ev.published ?? '—'} />
            <Meta icon={Globe} label="Domain" value={ev.domain} />
            <Meta
              icon={ev.fetchSuccess ? CheckCircle2 : XCircle}
              label="Fetch success"
              value={String(ev.fetchSuccess)}
              tone={ev.fetchSuccess ? 'text-emerald-600' : 'text-rose-600'}
            />
            <Meta icon={FileText} label="Extracted length" value={`${ev.textLength.toLocaleString()} chars`} />
          </dl>

          <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3 text-xs">
            <a
              href={ev.canonicalUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-brand-600 hover:underline"
            >
              <ExternalLink className="h-3.5 w-3.5" /> Canonical URL
            </a>
            <span className="truncate text-slate-400">{ev.sourceUrl}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function Meta({ icon: Icon, label, value, tone = 'text-slate-700' }) {
  return (
    <div>
      <dt className="mb-0.5 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
        <Icon className="h-3 w-3" /> {label}
      </dt>
      <dd className={`truncate font-medium ${tone}`}>{value}</dd>
    </div>
  )
}
