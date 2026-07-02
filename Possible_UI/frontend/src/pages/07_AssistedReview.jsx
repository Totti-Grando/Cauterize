import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Send, Loader2, Wand2, RefreshCw, Save, Check } from 'lucide-react'
import ChatShell from '../components/ChatShell'
import ChatTurn from '../components/ChatTurn'
import RunInfoPanel from '../components/RunInfoPanel'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import ExportButton from '../components/ExportButton'
import { Textarea, EmptyState } from '../components/ui'
import { useRun } from '../context/RunContext'
import { useEvalStream } from '../lib/useEvalStream'
import { saveRunFrom } from '../lib/saveRun'
import { api } from '../api'

// Assisted mode — the evaluator model drafts an EDITABLE question for you; you tweak it
// and send. Same chat + evaluation as manual, with an AI draft pre-filling the composer.
export default function AssistedReview() {
  const navigate = useNavigate()
  const { run, summary, update } = useRun()
  const stream = useEvalStream()
  const [draft, setDraft] = useState('')
  const [tips, setTips] = useState([])
  const [drafting, setDrafting] = useState(false)
  const [seq, setSeq] = useState(0)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const save = async () => {
    setSaving(true)
    const rec = await saveRunFrom(run, summary, stream.turns)
    setSaving(false)
    if (rec) {
      setSaved(true)
      setTimeout(() => navigate('/history'), 600)
    }
  }

  const generateDraft = async () => {
    setDrafting(true)
    try {
      const d = await api.draftQuestion(run.provider, seq)
      setDraft(d.text || '')
      setTips(d.tips || [])
      setSeq((s) => s + 1)
    } finally {
      setDrafting(false)
    }
  }

  // Produce the first editable draft from the model as soon as the page opens.
  useEffect(() => { generateDraft() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const send = () => {
    const q = draft.trim()
    if (!q || stream.running) return
    setDraft('')
    setTips([])
    update({ status: 'Running' })
    stream.ask(q, run.provider, undefined, run.objective)
  }

  const last = stream.turns[stream.turns.length - 1]
  const scrollKey = `${stream.turns.length}:${last?.answer ? 1 : 0}:${last?.evaluation ? 1 : 0}`

  return (
    <ChatShell
      title="Assisted Chat"
      subtitle={`Drafts by ${summary.primaryModelLabel} · answers from ${summary.providerLabel}`}
      statusChip={
        <StatusChip tone={stream.running ? 'warning' : 'success'} size="xs" dot pulse={stream.running}>
          {stream.running ? 'Running' : 'Ready'}
        </StatusChip>
      }
      headerActions={
        <>
          <ExportButton size="sm" label="Export" />
          <Button
            size="sm"
            variant="success"
            icon={saving ? Loader2 : saved ? Check : Save}
            onClick={save}
            disabled={saving || stream.turns.every((t) => !t.evaluation)}
          >
            {saved ? 'Saved' : saving ? 'Saving…' : 'Save run'}
          </Button>
        </>
      }
      runInfo={<RunInfoPanel summary={summary} metrics={stream.metrics} log={stream.log} lessons={stream.lessons} />}
      scrollKey={scrollKey}
      composer={
        <div className="space-y-2">
          {(tips.length > 0 || drafting) && (
            <div className="rounded-lg border border-brand-100 bg-brand-50/60 px-3 py-2 text-xs">
              <div className="mb-1 flex items-center gap-1.5 font-semibold text-brand-700">
                <Wand2 className="h-3.5 w-3.5" /> Draft from {summary.primaryModelLabel} — edit before sending
              </div>
              {drafting ? (
                <span className="inline-flex items-center gap-2 text-brand-700/80"><Loader2 className="h-3.5 w-3.5 animate-spin" /> drafting…</span>
              ) : (
                <ul className="list-inside list-disc space-y-0.5 text-brand-700/80">
                  {tips.map((t, i) => (<li key={i}>{t}</li>))}
                </ul>
              )}
            </div>
          )}
          <div className="flex items-end gap-2">
            <Textarea
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="Your question (editable draft)…"
              className="min-h-[52px]"
            />
            <div className="flex shrink-0 flex-col gap-2">
              <Button size="sm" variant="secondary" icon={drafting ? Loader2 : RefreshCw} onClick={generateDraft} disabled={drafting}>
                New draft
              </Button>
              <Button size="sm" icon={stream.running ? Loader2 : Send} onClick={send} disabled={stream.running}>
                Ask
              </Button>
            </div>
          </div>
        </div>
      }
    >
      {stream.turns.length === 0 ? (
        <div className="pt-16">
          <EmptyState
            icon={Wand2}
            title="Review the drafted question"
            description="The evaluator model drafted a question below — edit it or generate a new one, then click Ask to send it to the provider and evaluate the answer."
          />
        </div>
      ) : (
        <div className="space-y-8">
          {stream.turns.map((t) => (
            <ChatTurn key={t.key} turn={t} evaluatorLabel={summary.primaryModelLabel} lessons={stream.lessons} />
          ))}
        </div>
      )}
    </ChatShell>
  )
}
