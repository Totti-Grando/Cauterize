import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Target } from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import Stepper from '../components/Stepper'
import { Card } from '../components/Card'
import Button from '../components/Button'
import ModeCard from '../components/ModeCard'
import StatusChip from '../components/StatusChip'
import { Field, Select, Checkbox, Disclosure } from '../components/ui'
import { api } from '../api'
import { FOCUS_AREAS } from '../data/placeholders'
import { useRun } from '../context/RunContext'

const DEST = { manual: '/workspace', assisted: '/assisted', automatic: '/monitor' }

export default function QAMode() {
  const navigate = useNavigate()
  const { run, update } = useRun()
  const [modes, setModes] = useState([])
  const [mode, setMode] = useState(run.mode ?? 'assisted')
  const [objective, setObjective] = useState(run.objective ?? 'learning')
  const [count, setCount] = useState(run.questionCount)
  const [difficulty, setDifficulty] = useState(run.difficultyMix)
  const [focus, setFocus] = useState(run.focusAreas)

  useEffect(() => {
    api.getModes().then(setModes)
  }, [])

  const toggleFocus = (f) => setFocus((arr) => (arr.includes(f) ? arr.filter((x) => x !== f) : [...arr, f]))

  const cont = () => {
    update({ mode, objective, questionCount: count, difficultyMix: difficulty, focusAreas: focus })
    navigate(DEST[mode] ?? '/workspace')
  }

  const OBJECTIVES = [
    { id: 'learning', name: 'Learning', desc: 'Layer B lessons sharpen the evaluation each turn — your question is sent as-is.' },
    { id: 'attack', name: 'Attack (red-team)', desc: 'Lessons escalate the probe against the configured provider to test its robustness. Adversarial checks (leak / injection / fabrication) score whether the attack lands.' },
  ]

  return (
    <PageContainer>
      <PageHeader
        title="Q&A Generation Mode"
        description="Choose how much control you want over question generation."
        actions={
          <Button onClick={cont} iconRight={ArrowRight}>
            Open Evaluation Workspace
          </Button>
        }
      />
      <Card className="mb-6 px-6 py-4">
        <Stepper current={2} />
      </Card>

      <div className="mb-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        {modes.map((m) => (
          <ModeCard key={m.id} mode={m} selected={mode === m.id} onSelect={() => setMode(m.id)} />
        ))}
      </div>

      {/* Layer B objective — compact segmented choice */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-800">
              <Target className="h-4 w-4 text-slate-400" /> Layer B objective
            </div>
            <div className="text-xs text-slate-500">How lessons learned each turn are used</div>
          </div>
          <div className="inline-flex items-center gap-1 rounded-lg bg-slate-100 p-1 sm:ml-auto">
            {OBJECTIVES.map((o) => {
              const on = objective === o.id
              const attack = o.id === 'attack'
              return (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => setObjective(o.id)}
                  className={`focusable rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    on
                      ? `bg-white shadow-sm ${attack ? 'text-rose-700' : 'text-brand-700'}`
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  {o.name}
                </button>
              )
            })}
          </div>
        </div>
        <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-slate-500">
          {objective === 'attack' && <StatusChip tone="danger" size="xs">red-team</StatusChip>}
          <span>{OBJECTIVES.find((o) => o.id === objective)?.desc}</span>
        </p>
      </div>

      {/* Generation parameters — collapsed by default; defaults shown in the summary */}
      <Disclosure
        icon={Target}
        title="Advanced generation options"
        summary={`${count} questions · ${difficulty} · ${focus.length} focus area${focus.length === 1 ? '' : 's'}`}
      >
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Field label="Question count">
            <Select value={count} onChange={(e) => setCount(Number(e.target.value))}>
              {[3, 5, 8, 10, 15, 20].map((n) => (
                <option key={n} value={n}>
                  {n} questions
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Difficulty mix">
            <Select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              {['Balanced', 'Mostly Easy', 'Mostly Medium', 'Mostly Hard', 'Easy / Medium / Hard'].map((d) => (
                <option key={d}>{d}</option>
              ))}
            </Select>
          </Field>
          <div className="lg:col-span-1">
            <div className="mb-1.5 text-xs font-semibold text-slate-600">Selected difficulty band</div>
            <div className="flex gap-1.5">
              {['Easy', 'Medium', 'Hard'].map((d, i) => (
                <span
                  key={d}
                  className={`flex-1 rounded-md px-2 py-2 text-center text-xs font-medium ${
                    ['bg-emerald-50 text-emerald-700', 'bg-amber-50 text-amber-700', 'bg-rose-50 text-rose-700'][i]
                  }`}
                >
                  {d}
                </span>
              ))}
            </div>
          </div>

          <div className="lg:col-span-3">
            <div className="mb-2 text-xs font-semibold text-slate-600">Focus areas</div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-3 lg:grid-cols-4">
              {FOCUS_AREAS.map((f) => (
                <Checkbox key={f} checked={focus.includes(f)} onChange={() => toggleFocus(f)} label={f} />
              ))}
            </div>
          </div>
        </div>
      </Disclosure>
    </PageContainer>
  )
}
