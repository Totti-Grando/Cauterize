import { useRef, useState } from 'react'
import { api } from '../api'

/**
 * Shared streaming state for the chat-style mode pages (manual / assisted / automatic).
 * Consumes the SSE events into a chat transcript (`turns`) plus a live `log`, `metrics`, and
 * accumulated Layer B `lessons`. Manual/assisted append one turn per question and REPLAY the
 * accumulated lessons on each subsequent turn; automatic streams the Layer B loop.
 */
export function useEvalStream() {
  const [turns, setTurns] = useState([]) // {key, questionId, question, original, answer, provider, evaluation, lessons}
  const [log, setLog] = useState([])
  const [metrics, setMetrics] = useState([])
  const [lessons, setLessons] = useState([]) // accumulated deduped {text, kind}
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [live, setLive] = useState(null)
  const [statusLine, setStatusLine] = useState('')
  const curRef = useRef(-1)
  const abortRef = useRef(null)
  const lessonsRef = useRef([])       // mirror of `lessons` so ask() sends the latest
  const pendingEsc = useRef(null)     // escalated_question arrives just before its question

  const now = () => new Date().toLocaleTimeString('en-GB')
  const pushLog = (step, status, message) => setLog((l) => [...l, { ts: now(), step, status, message }])

  const mergeLessons = (incoming) => {
    const seen = new Set(lessonsRef.current.map((l) => l.text))
    const fresh = (incoming || []).filter((l) => !seen.has(l.text))
    if (!fresh.length) return
    lessonsRef.current = [...lessonsRef.current, ...fresh]
    setLessons([...lessonsRef.current])
  }

  const onEvent = (ev) => {
    switch (ev.type) {
      case 'escalated_question':
        pendingEsc.current = { original: ev.original, escalated: ev.text }
        break
      case 'question':
        setTurns((t) => {
          curRef.current = t.length
          const esc = pendingEsc.current
          pendingEsc.current = null
          return [...t, {
            key: `${t.length}-${ev.id}`, questionId: ev.id, question: ev.text,
            original: esc ? esc.original : null, answer: '', provider: null, evaluation: null, lessons: [],
          }]
        })
        break
      case 'answer': {
        const i = curRef.current
        setTurns((t) => t.map((x, idx) => (idx === i ? { ...x, answer: ev.text, provider: ev.provider } : x)))
        break
      }
      case 'evaluation': {
        const i = curRef.current
        setTurns((t) => t.map((x, idx) => (idx === i ? { ...x, evaluation: ev.evaluation } : x)))
        pushLog('Evaluation', 'success', `${ev.evaluation.questionId} → ${ev.evaluation.verdict}`)
        break
      }
      case 'lessons': {
        const round = [...(ev.promptable || []), ...(ev.structural || [])]
        const i = curRef.current
        setTurns((t) => t.map((x, idx) => (idx === i ? { ...x, lessons: round } : x)))
        mergeLessons(round)
        pushLog('Lessons', 'info', `${round.length} lesson(s) — ${ev.objective || ''}`)
        break
      }
      case 'step':
        pushLog(ev.step, ev.status || 'active', ev.message || '')
        setStatusLine(ev.step)
        break
      case 'log':
        pushLog(ev.step, ev.status || 'info', ev.message || '')
        break
      case 'metric':
        setMetrics(ev.metrics)
        break
      case 'done':
        setRunning(false)
        setDone(true)
        setLive(ev.live)
        setStatusLine(ev.live ? 'Complete (live)' : 'Complete (offline demo)')
        break
      default:
        break
    }
  }

  const _start = async (fn) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setRunning(true)
    setDone(false)
    try {
      await fn(controller.signal)
    } catch (e) {
      if (e.name !== 'AbortError') {
        pushLog('Run', 'error', e.message)
        setRunning(false)
      }
    }
  }

  // Manual / assisted: append one turn; replays the accumulated lessons + objective.
  const ask = (question, provider, context, objective = 'learning') =>
    _start((signal) => api.manualTurn(
      { question, context, provider, objective, lessons: lessonsRef.current }, onEvent, { signal }))

  // Automatic: clear and stream the Layer B loop for the objective.
  const runBatch = ({ mode, provider, questionCount, objective = 'learning' }) => {
    setTurns([]); setMetrics([]); setLog([]); setLessons([])
    lessonsRef.current = []; curRef.current = -1
    return _start((signal) => api.runStream({ mode, provider, questionCount, objective }, onEvent, { signal }))
  }

  const stop = () => abortRef.current?.abort()
  const reset = () => {
    stop()
    setTurns([]); setLog([]); setMetrics([]); setLessons([]); setDone(false); setRunning(false)
    setStatusLine(''); curRef.current = -1; lessonsRef.current = []; pendingEsc.current = null
  }

  return { turns, log, metrics, lessons, running, done, live, statusLine, ask, runBatch, stop, reset }
}
