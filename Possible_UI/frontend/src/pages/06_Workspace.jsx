import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Send, Loader2, Save, Sparkles, Check } from 'lucide-react'
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

// Manual mode — a plain chat: you ask, the provider answers, the answer is evaluated.
export default function Workspace() {
  const navigate = useNavigate()
  const { run, summary, update } = useRun()
  const stream = useEvalStream()
  const [draft, setDraft] = useState('')
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

  const send = () => {
    const q = draft.trim()
    if (!q || stream.running) return
    setDraft('')
    update({ status: 'Running' })
    stream.ask(q, run.provider, undefined, run.objective)
  }

  const last = stream.turns[stream.turns.length - 1]
  const scrollKey = `${stream.turns.length}:${last?.answer ? 1 : 0}:${last?.evaluation ? 1 : 0}`

  return (
    <ChatShell
      title="Manual Chat"
      subtitle={`Ask ${summary.providerLabel} · evaluated by ${summary.primaryModelLabel}`}
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
        <div className="flex items-end gap-2">
          <Textarea
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Message the provider…  (Enter to send · Shift+Enter for a new line)"
            className="min-h-[44px]"
          />
          <Button icon={stream.running ? Loader2 : Send} onClick={send} disabled={stream.running} className="shrink-0">
            Send
          </Button>
        </div>
      }
    >
      {stream.turns.length === 0 ? (
        <div className="pt-16">
          <EmptyState
            icon={Sparkles}
            title="Ask your first question"
            description="Type a question below. It goes to the provider, and the answer is evaluated for groundedness, accuracy, and shortfalls."
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
