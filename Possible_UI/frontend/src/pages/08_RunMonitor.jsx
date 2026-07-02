import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, RotateCw, Loader2, Workflow } from 'lucide-react'
import ChatShell from '../components/ChatShell'
import ChatTurn from '../components/ChatTurn'
import RunInfoPanel from '../components/RunInfoPanel'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import { EmptyState } from '../components/ui'
import { useRun } from '../context/RunContext'
import { useEvalStream } from '../lib/useEvalStream'
import { saveRunFrom } from '../lib/saveRun'

// Automatic mode — the pipeline runs itself and streams each question/answer/evaluation
// into the chat. Progress, metrics and the log live in the "Run info" drawer.
export default function RunMonitor() {
  const navigate = useNavigate()
  const { run, summary, update } = useRun()
  const stream = useEvalStream()
  const [saved, setSaved] = useState(false)
  const savedRef = useRef(false)

  const start = () => {
    savedRef.current = false
    setSaved(false)
    update({ status: 'Running' })
    stream.runBatch({ mode: run.mode, provider: run.provider, questionCount: run.questionCount, objective: run.objective })
  }

  useEffect(() => {
    start()
    return () => stream.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // On completion: mark done and auto-save the run to history (once).
  useEffect(() => {
    if (!stream.done || savedRef.current) return
    savedRef.current = true
    update({ status: 'Complete' })
    saveRunFrom(run, summary, stream.turns).then((rec) => rec && setSaved(true))
  }, [stream.done]) // eslint-disable-line react-hooks/exhaustive-deps

  const completed = stream.turns.filter((t) => t.evaluation).length
  const metricTotal = stream.metrics.find((m) => m.label === 'Questions')?.value
  const total = metricTotal || run.questionCount || stream.turns.length || 5
  const pct = total ? Math.min(100, Math.round((completed / total) * 100)) : 0
  const scrollKey = `${stream.turns.length}:${completed}:${stream.done ? 1 : 0}`

  return (
    <ChatShell
      title="Automatic Run"
      subtitle={`${summary.providerLabel} · evaluated by ${summary.primaryModelLabel}`}
      statusChip={
        <StatusChip tone={stream.done ? 'success' : 'warning'} size="xs" dot pulse={stream.running}>
          {stream.done ? 'Complete' : stream.running ? 'Running' : 'Idle'} · {completed}/{total}
        </StatusChip>
      }
      headerActions={
        <>
          <Button size="sm" variant="secondary" icon={stream.running ? Loader2 : RotateCw} onClick={start} disabled={stream.running}>
            {stream.running ? 'Running…' : 'Re-run'}
          </Button>
          <Button size="sm" icon={ArrowRight} onClick={() => navigate('/results')} disabled={!stream.done}>
            Results
          </Button>
        </>
      }
      runInfo={<RunInfoPanel summary={summary} metrics={stream.metrics} log={stream.log} lessons={stream.lessons} progress={{ completed, total, pct, done: stream.done }} />}
      scrollKey={scrollKey}
    >
      {stream.turns.length === 0 ? (
        <div className="pt-16">
          <EmptyState
            icon={Workflow}
            title="Starting the automatic run…"
            description="Questions are generated, sent to the provider, and evaluated one by one. They'll appear here as they complete."
          />
        </div>
      ) : (
        <div className="space-y-8">
          {stream.turns.map((t) => (
            <ChatTurn key={t.key} turn={t} evaluatorLabel={summary.primaryModelLabel} lessons={stream.lessons} />
          ))}
          {stream.done && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm">
              <span className="font-semibold text-emerald-900">Run complete</span>
              <span className="text-emerald-700"> — {completed} evaluated{saved ? ' · saved to history' : ''}. </span>
              <button onClick={() => navigate('/results')} className="font-semibold text-emerald-800 underline">View results →</button>
              <span className="text-emerald-700"> · </span>
              <button onClick={() => navigate('/history')} className="font-semibold text-emerald-800 underline">Run history →</button>
            </div>
          )}
        </div>
      )}
    </ChatShell>
  )
}
