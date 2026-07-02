import { Copy, Check, Braces } from 'lucide-react'
import { useCopied } from './ui'

// Read-only JSON panel with copy button — used for evaluation JSON output.
export default function JsonViewer({ data, title = 'Evaluation JSON', className = '' }) {
  const [copied, copy] = useCopied()
  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  return (
    <div className={`overflow-hidden rounded-lg border border-navy-700 bg-navy-900 ${className}`}>
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
        <span className="flex items-center gap-2 text-xs font-medium text-slate-300">
          <Braces className="h-3.5 w-3.5 text-brand-300" /> {title}
        </span>
        <button
          onClick={() => copy(text)}
          className="focusable flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium text-slate-400 hover:bg-white/5 hover:text-slate-200"
        >
          {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="max-h-80 overflow-auto px-3 py-3 font-mono text-[11.5px] leading-relaxed text-slate-200">
        {syntaxHighlight(text)}
      </pre>
    </div>
  )
}

// Lightweight token coloring without a dependency.
function syntaxHighlight(json) {
  const parts = []
  const regex = /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g
  let last = 0
  let m
  let i = 0
  while ((m = regex.exec(json)) !== null) {
    parts.push(json.slice(last, m.index))
    let cls = 'text-amber-300' // number
    const token = m[0]
    if (/^"/.test(token)) {
      cls = /:$/.test(token) ? 'text-brand-300' : 'text-emerald-300'
    } else if (/true|false/.test(token)) {
      cls = 'text-sky-300'
    } else if (/null/.test(token)) {
      cls = 'text-slate-500'
    }
    parts.push(
      <span key={i++} className={cls}>
        {token}
      </span>,
    )
    last = m.index + token.length
  }
  parts.push(json.slice(last))
  return parts
}
