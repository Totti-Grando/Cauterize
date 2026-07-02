import { useNavigate } from 'react-router-dom'
import {
  FolderUp,
  Cpu,
  ListChecks,
  Play,
  BarChart3,
  Download,
  Plus,
  FolderOpen,
  ArrowRight,
} from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import Stepper from '../components/Stepper'
import { Card } from '../components/Card'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import { useRun } from '../context/RunContext'

const STEPS = [
  { icon: FolderUp, title: 'Sources', desc: 'Upload documents or add research links to ground the evaluation.', to: '/sources' },
  { icon: Cpu, title: 'Models', desc: 'Pick the primary Bedrock evaluator and the secondary provider to test.', to: '/models' },
  { icon: ListChecks, title: 'Q&A Mode', desc: 'Choose manual, assisted, or fully automatic question generation.', to: '/qa-mode' },
  { icon: Play, title: 'Run', desc: 'Send questions to the provider and evaluate every answer.', to: '/workspace' },
  { icon: BarChart3, title: 'Review', desc: 'Inspect verdicts, groundedness, shortfalls, and evidence.', to: '/results' },
  { icon: Download, title: 'Export', desc: 'Export CSV / JSON and save an auditable run to history.', to: '/history' },
]

function SummaryRow({ label, value, tone }) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-xs text-slate-500">{label}</span>
      {tone ? <StatusChip tone={tone}>{value}</StatusChip> : <span className="text-sm font-medium text-slate-800">{value}</span>}
    </div>
  )
}

export default function StoryDashboard() {
  const navigate = useNavigate()
  const { run, summary } = useRun()

  return (
    <PageContainer>
      <PageHeader
        title="Story Mode Dashboard"
        description="Walk through a structured, left-to-right evaluation journey. Each step builds the run that flows into the workspace and results."
        actions={
          <>
            <Button variant="secondary" icon={FolderOpen} onClick={() => navigate('/history')}>
              Open Previous Run
            </Button>
            <Button icon={Plus} onClick={() => navigate('/sources')}>
              Start New Evaluation Story
            </Button>
          </>
        }
      />

      <Card className="mb-6 px-6 py-5">
        <Stepper current={0} />
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Step cards */}
        <div className="lg:col-span-2">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {STEPS.map((s, i) => (
              <Card
                key={s.title}
                hover
                as="button"
                onClick={() => navigate(s.to)}
                className="focusable flex flex-col items-start p-5 text-left"
              >
                <div className="mb-3 flex w-full items-center justify-between">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                    <s.icon className="h-5 w-5" />
                  </span>
                  <span className="text-xs font-semibold text-slate-300">0{i + 1}</span>
                </div>
                <div className="text-sm font-semibold text-slate-900">{s.title}</div>
                <p className="mt-1 flex-1 text-xs leading-relaxed text-slate-500">{s.desc}</p>
                <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-brand-600">
                  Go to step <ArrowRight className="h-3.5 w-3.5" />
                </span>
              </Card>
            ))}
          </div>
        </div>

        {/* Current run summary */}
        <div>
          <Card className="sticky top-4 overflow-hidden">
            <div className="border-b border-slate-100 bg-slate-50 px-5 py-3.5">
              <h3 className="text-sm font-semibold text-slate-900">Current Run Summary</h3>
              <p className="text-xs text-slate-400">Updates as you complete each step</p>
            </div>
            <div className="divide-y divide-slate-100 px-5">
              <SummaryRow label="Documents" value={summary.documents} />
              <SummaryRow label="Links" value={summary.links} />
              <SummaryRow label="Primary model" value={summary.primaryModelLabel} />
              <SummaryRow label="Secondary provider" value={summary.providerLabel} />
              <SummaryRow label="Mode" value={summary.modeLabel} />
              <SummaryRow label="Status" value={run.status} tone="neutral" />
            </div>
            <div className="px-5 py-4">
              <Button className="w-full" onClick={() => navigate('/sources')} iconRight={ArrowRight}>
                Continue Setup
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </PageContainer>
  )
}
