import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, AlertTriangle, ArrowRight, FileCheck2 } from 'lucide-react'
import { Checkbox } from '../components/ui'
import Button from '../components/Button'
import { useRun } from '../context/RunContext'

const TERMS = [
  {
    h: '1. Purpose & scope',
    p: 'Q&A Evaluation Studio is an internal tool for evaluating and auditing AI-generated answers across documents and research providers. It is intended for model-evaluation and research-support workflows only, and is not a system of record.',
  },
  {
    h: '2. Human review required',
    p: 'All generated questions, provider answers, and automated evaluations are decision-support outputs. They may contain errors, omissions, or hallucinations and must be reviewed by a qualified person before any downstream use.',
  },
  {
    h: '3. Data handling',
    p: 'Do not upload confidential, restricted, or customer-identifying material unless you are explicitly authorized to do so. Sources and links you add may be transmitted to the configured evaluation models and secondary providers.',
  },
  {
    h: '4. Provider outputs',
    p: 'Secondary providers (e.g. RavenPack, Nexa) operate under their own terms. Groundedness, evidence, and shortfall classifications are produced by the primary evaluation model and are themselves subject to review.',
  },
  {
    h: '5. Auditability',
    p: 'Evaluation runs, configuration snapshots, and exports are retained for audit purposes. Exports may contain source excerpts; handle exported files according to your data-classification policy.',
  },
]

export default function Terms() {
  const navigate = useNavigate()
  const { update } = useRun()
  const [evalOnly, setEvalOnly] = useState(false)
  const [reviewOk, setReviewOk] = useState(false)
  const canStart = evalOnly && reviewOk

  const accept = () => {
    update({ termsAccepted: true, status: 'Configuring' })
    navigate('/dashboard')
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-900 px-4 py-10">
      {/* subtle backdrop */}
      <div className="pointer-events-none fixed inset-0 grid-backdrop opacity-[0.06]" />
      <div className="relative w-full max-w-2xl">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600 text-white shadow-panel">
            <ShieldCheck className="h-7 w-7" />
          </span>
          <h1 className="text-2xl font-bold tracking-tight text-white">Q&A Evaluation Studio</h1>
          <p className="mt-2 max-w-md text-sm text-slate-400">
            Generate, test, evaluate, and audit AI answers across documents and research providers.
          </p>
        </div>

        <div className="overflow-hidden rounded-2xl bg-white shadow-panel">
          <div className="flex items-center gap-2 border-b border-slate-100 px-6 py-4">
            <FileCheck2 className="h-4 w-4 text-brand-600" />
            <h2 className="text-sm font-semibold text-slate-900">Terms &amp; Conditions</h2>
            <span className="ml-auto text-xs text-slate-400">Please read before continuing</span>
          </div>

          <div className="max-h-72 space-y-4 overflow-y-auto px-6 py-5">
            {TERMS.map((t) => (
              <div key={t.h}>
                <h3 className="text-sm font-semibold text-slate-800">{t.h}</h3>
                <p className="mt-1 text-sm leading-relaxed text-slate-500">{t.p}</p>
              </div>
            ))}
          </div>

          <div className="space-y-3 border-t border-slate-100 bg-slate-50 px-6 py-5">
            <Checkbox
              checked={evalOnly}
              onChange={setEvalOnly}
              label="I understand this tool is for evaluation and research support only."
            />
            <Checkbox
              checked={reviewOk}
              onChange={setReviewOk}
              label="I understand generated outputs require human review."
            />

            <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              Do not upload confidential material unless authorized.
            </div>

            <div className="flex justify-end pt-1">
              <Button onClick={accept} disabled={!canStart} iconRight={ArrowRight} size="lg">
                Accept and Start
              </Button>
            </div>
          </div>
        </div>

        <p className="mt-4 text-center text-xs text-slate-500">Internal use only · Responsible AI Operations</p>
      </div>
    </div>
  )
}
