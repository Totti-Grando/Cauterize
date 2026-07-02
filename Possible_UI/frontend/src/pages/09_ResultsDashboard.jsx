import { useEffect, useState } from 'react'
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  ListChecks,
  CheckCircle2,
  AlertCircle,
  XCircle,
  HelpCircle,
  ShieldCheck,
  ShieldX,
  Flame,
  FileWarning,
  BarChart3,
} from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import { Card, CardHeader } from '../components/Card'
import MetricCard from '../components/MetricCard'
import ResultsTable from '../components/ResultsTable'
import ExportButton from '../components/ExportButton'
import { Disclosure } from '../components/ui'
import { api } from '../api'

const COLORS = {
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#f43f5e',
  info: '#0ea5e9',
  brand: '#2563eb',
  slate: '#94a3b8',
  violet: '#8b5cf6',
}

export default function ResultsDashboard() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getEvaluations().then((d) => {
      setRows(d)
      setLoading(false)
    })
  }, [])

  const count = (pred) => rows.filter(pred).length
  const verdicts = {
    correct: count((e) => e.verdict === 'correct'),
    partial: count((e) => e.verdict === 'partial'),
    incorrect: count((e) => e.verdict === 'incorrect'),
    unverifiable: count((e) => e.verdict === 'unverifiable'),
  }
  const grounded = count((e) => e.grounded)
  const ungrounded = rows.length - grounded
  const hallucinations = count((e) => e.shortfalls.includes('unsupported_claim') || e.shortfalls.includes('overclaimed_materiality'))
  const missingInfo = count((e) => e.shortfalls.includes('missing_information'))

  const verdictData = [
    { name: 'Correct', value: verdicts.correct, key: 'success' },
    { name: 'Partial', value: verdicts.partial, key: 'warning' },
    { name: 'Incorrect', value: verdicts.incorrect, key: 'danger' },
    { name: 'Unverifiable', value: verdicts.unverifiable, key: 'info' },
  ]

  const shortfallCounts = {}
  rows.forEach((e) => e.shortfalls.forEach((s) => (shortfallCounts[s] = (shortfallCounts[s] || 0) + 1)))
  const shortfallData = Object.entries(shortfallCounts).map(([k, v]) => ({ name: k.replace(/_/g, ' '), value: v }))

  const categoryData = [
    { name: 'Reputational', correct: 0, partial: 1, incorrect: 0 },
    { name: 'Regulatory', correct: 1, partial: 0, incorrect: 0 },
    { name: 'Sentiment', correct: 0, partial: 1, incorrect: 0 },
    { name: 'ESG', correct: 0, partial: 0, incorrect: 1 },
    { name: 'Liquidity', correct: 0, partial: 0, incorrect: 0 },
  ]

  const groundednessData = [
    { name: 'Documents', grounded: 2, partial: 1, ungrounded: 0 },
    { name: 'Newswire', grounded: 1, partial: 0, ungrounded: 0 },
    { name: 'Research', grounded: 0, partial: 1, ungrounded: 1 },
    { name: 'Portal', grounded: 0, partial: 0, ungrounded: 1 },
  ]

  return (
    <PageContainer>
      <PageHeader
        title="Results Dashboard"
        description="Verdicts, groundedness, and shortfalls across the run."
        actions={<ExportButton label="Export results" variant="primary" />}
      />

      {/* Key metrics — the headline numbers */}
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <MetricCard label="Total questions" value={rows.length} icon={ListChecks} tone="brand" />
        <MetricCard label="Correct" value={verdicts.correct} icon={CheckCircle2} tone="success" />
        <MetricCard label="Partial" value={verdicts.partial} icon={AlertCircle} tone="warning" />
        <MetricCard label="Incorrect" value={verdicts.incorrect} icon={XCircle} tone="danger" />
        <MetricCard label="Grounded answers" value={grounded} icon={ShieldCheck} tone="success" />
      </div>

      {/* Verdict distribution — the one chart worth leading with */}
      <Card className="mb-6">
        <CardHeader title="Verdict distribution" />
        <div className="mx-auto h-64 max-w-lg px-4 py-4">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={verdictData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>
                {verdictData.map((d) => (
                  <Cell key={d.name} fill={COLORS[d.key]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend iconType="circle" />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Everything else, collapsed — secondary metrics + breakdown charts */}
      <Disclosure
        className="mb-6"
        icon={BarChart3}
        title="More analytics"
        summary={`${verdicts.unverifiable} unverifiable · ${ungrounded} ungrounded · ${hallucinations} hallucination · ${missingInfo} missing-info`}
      >
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <MetricCard label="Unverifiable" value={verdicts.unverifiable} icon={HelpCircle} tone="info" />
          <MetricCard label="Ungrounded answers" value={ungrounded} icon={ShieldX} tone="danger" />
          <MetricCard label="Hallucination flags" value={hallucinations} icon={Flame} tone="danger" />
          <MetricCard label="Missing info flags" value={missingInfo} icon={FileWarning} tone="warning" />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Shortfall distribution" />
            <div className="h-64 px-4 py-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shortfallData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: '#64748b' }} allowDecimals={false} />
                  <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11, fill: '#64748b' }} />
                  <Tooltip cursor={{ fill: '#f8fafc' }} />
                  <Bar dataKey="value" fill={COLORS.warning} radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <CardHeader title="Provider performance by category" />
            <div className="h-64 px-4 py-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} allowDecimals={false} />
                  <Tooltip cursor={{ fill: '#f8fafc' }} />
                  <Legend iconType="circle" />
                  <Bar dataKey="correct" stackId="a" fill={COLORS.success} radius={[0, 0, 0, 0]} barSize={26} />
                  <Bar dataKey="partial" stackId="a" fill={COLORS.warning} barSize={26} />
                  <Bar dataKey="incorrect" stackId="a" fill={COLORS.danger} radius={[4, 4, 0, 0]} barSize={26} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card>
            <CardHeader title="Groundedness by source type" />
            <div className="h-64 px-4 py-4">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={groundednessData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#64748b' }} allowDecimals={false} />
                  <Tooltip cursor={{ fill: '#f8fafc' }} />
                  <Legend iconType="circle" />
                  <Bar dataKey="grounded" stackId="b" fill={COLORS.success} barSize={26} />
                  <Bar dataKey="partial" stackId="b" fill={COLORS.warning} barSize={26} />
                  <Bar dataKey="ungrounded" stackId="b" fill={COLORS.danger} radius={[4, 4, 0, 0]} barSize={26} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </Disclosure>

      {/* Results table */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Results detail</h2>
        <span className="text-xs text-slate-400">{rows.length} rows</span>
      </div>
      {loading ? (
        <div className="h-48 animate-pulse rounded-xl bg-slate-200/60" />
      ) : (
        <ResultsTable rows={rows} />
      )}
    </PageContainer>
  )
}
