import { useEffect, useState } from 'react'
import {
  Cpu,
  Boxes,
  Cloud,
  ListChecks,
  ScanSearch,
  FileSpreadsheet,
  ScrollText,
  Database,
  Save,
  Plus,
  Trash2,
  RefreshCw,
  Plug,
  Loader2,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import { Card, CardHeader, CardBody } from '../components/Card'
import Button from '../components/Button'
import StatusChip from '../components/StatusChip'
import { Field, Input, Select, Toggle, Checkbox } from '../components/ui'
import RubricConfig from '../components/RubricConfig'
import { api } from '../api'
import { FOCUS_AREAS } from '../data/placeholders'

const SECTIONS = [
  { key: 'aws', label: 'AWS credentials', icon: Cloud },
  { key: 'bedrock', label: 'Bedrock models', icon: Cpu },
  { key: 'provider', label: 'Secondary providers', icon: Boxes },
  { key: 'eval', label: 'Evaluation rubric', icon: ScanSearch },
  { key: 's3', label: 'Long-term storage', icon: Database },
  { key: 'csv', label: 'CSV export schema', icon: FileSpreadsheet },
  { key: 'audit', label: 'Logging & audit', icon: ScrollText },
]

const CSV_COLUMNS = [
  'question_id', 'question', 'provider', 'provider_answer', 'verdict', 'grounded',
  'source_groundedness', 'shortfalls', 'missing_points', 'final_summary', 'evidence_count',
]

// A masked secret from the server looks like { configured, last4 }.
const isMasked = (v) => v && typeof v === 'object' && 'configured' in v

/** Password input that shows "configured" state and only reports a value when the user types. */
function SecretInput({ value, onChange, placeholder = 'Not set' }) {
  const configured = isMasked(value) && value.configured
  const typed = typeof value === 'string' ? value : ''
  return (
    <div className="flex items-center gap-2">
      <Input
        type="password"
        value={typed}
        onChange={(e) => onChange(e.target.value)}
        placeholder={configured ? `•••• ${value.last4}` : placeholder}
        className="font-mono text-xs"
      />
      {configured && typed === '' && <StatusChip tone="success" size="xs">set</StatusChip>}
    </div>
  )
}

function TestResult({ result }) {
  if (!result) return null
  const Icon = result.ok ? CheckCircle2 : XCircle
  return (
    <div className={`mt-2 flex items-start gap-1.5 text-xs ${result.ok ? 'text-emerald-600' : 'text-rose-600'}`}>
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span className="break-all">{result.detail}</span>
    </div>
  )
}

// Replace masked-secret objects with '' (the server treats '' as "unchanged, keep stored").
function toPatch(node) {
  if (Array.isArray(node)) return node.map(toPatch)
  if (isMasked(node)) return ''
  if (node && typeof node === 'object') {
    return Object.fromEntries(Object.entries(node).map(([k, v]) => [k, toPatch(v)]))
  }
  return node
}

export default function Settings() {
  const [section, setSection] = useState('aws')
  const [cfg, setCfg] = useState(null)
  const [models, setModels] = useState([])
  const [modelSource, setModelSource] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [testing, setTesting] = useState(null) // provider id or 'evaluator'
  const [testResult, setTestResult] = useState({})
  const [rubric, setRubric] = useState(null)

  // local-only cosmetic sections (not persisted server-side)
  const [csvCols, setCsvCols] = useState(CSV_COLUMNS)
  const [focus, setFocus] = useState(['Accuracy', 'Groundedness', 'Hallucination resistance', 'Missing information'])
  const [audit, setAudit] = useState({ retainRuns: true, logProvider: true, redactPii: true, verbose: false })

  useEffect(() => {
    api.getSettings().then(setCfg)
    api.getBedrockModels(false).then((d) => {
      setModels(d.models || [])
      setModelSource(d.detail || '')
    })
    api.getRubric().then(setRubric).catch(() => setRubric(null))
  }, [])

  const setPath = (path, value) =>
    setCfg((prev) => {
      const next = structuredClone(prev)
      let cur = next
      const parts = path.split('.')
      for (let i = 0; i < parts.length - 1; i++) cur = cur[parts[i]]
      cur[parts[parts.length - 1]] = value
      return next
    })

  const save = async () => {
    setSaving(true)
    const updated = await api.saveSettings(toPatch(cfg))
    setCfg(updated)
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 1800)
  }

  const refreshModels = async () => {
    setRefreshing(true)
    const d = await api.getBedrockModels(true)
    setModels(d.models || [])
    setModelSource(d.detail || '')
    setRefreshing(false)
  }

  const runTest = async (providerId) => {
    setTesting(providerId || 'evaluator')
    const r = await api.testSettings(providerId)
    setTestResult((prev) => ({ ...prev, evaluator: r.evaluator, ...(providerId ? { [providerId]: r.provider } : {}) }))
    setTesting(null)
  }

  const toggleModel = (id) => {
    const cur = cfg.bedrock.enabled_model_ids || []
    setPath('bedrock.enabled_model_ids', cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id])
  }
  const toggleFocus = (f) => setFocus((a) => (a.includes(f) ? a.filter((x) => x !== f) : [...a, f]))
  const toggleCol = (c) => setCsvCols((a) => (a.includes(c) ? a.filter((x) => x !== c) : [...a, c]))

  if (!cfg) {
    return (
      <PageContainer>
        <PageHeader title="Settings" description="Loading configuration…" />
        <div className="h-48 animate-pulse rounded-xl bg-slate-200/60" />
      </PageContainer>
    )
  }

  const enabledIds = cfg.bedrock.enabled_model_ids || []

  return (
    <PageContainer>
      <PageHeader
        title="Settings"
        description="Credentials and defaults for evaluation runs. Secrets are stored on the server and never displayed."
        actions={
          <Button icon={saving ? Loader2 : Save} variant={saved ? 'success' : 'primary'} onClick={save} disabled={saving}>
            {saved ? 'Saved' : saving ? 'Saving…' : 'Save settings'}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <Card className="h-fit p-2 lg:col-span-1">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              onClick={() => setSection(s.key)}
              className={`focusable flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors ${
                section === s.key ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <s.icon className="h-4 w-4" />
              {s.label}
            </button>
          ))}
        </Card>

        <div className="space-y-6 lg:col-span-3">
          {/* AWS */}
          {section === 'aws' && (
            <Card>
              <CardHeader
                title="AWS credentials"
                subtitle="Used for the Bedrock evaluator. Leave keys blank to use an AWS profile or IAM role."
                icon={Cloud}
                actions={
                  <Button size="sm" variant="secondary" icon={testing === 'evaluator' ? Loader2 : Plug} onClick={() => runTest(null)} disabled={testing === 'evaluator'}>
                    Test evaluator
                  </Button>
                }
              />
              <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="AWS region">
                  <Select value={cfg.aws.region} onChange={(e) => setPath('aws.region', e.target.value)}>
                    {['us-east-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-southeast-1'].map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Evaluator backend">
                  <Select value={cfg.evaluator.backend} onChange={(e) => setPath('evaluator.backend', e.target.value)}>
                    <option value="bedrock">Bedrock (AWS)</option>
                    <option value="anthropic">Anthropic (direct)</option>
                    <option value="groq">Groq</option>
                  </Select>
                </Field>
                <Field label="Access key ID">
                  <SecretInput value={cfg.aws.access_key_id} onChange={(v) => setPath('aws.access_key_id', v)} />
                </Field>
                <Field label="Secret access key">
                  <SecretInput value={cfg.aws.secret_access_key} onChange={(v) => setPath('aws.secret_access_key', v)} />
                </Field>
                <Field label="Session token" hint="Optional (temporary credentials).">
                  <SecretInput value={cfg.aws.session_token} onChange={(v) => setPath('aws.session_token', v)} />
                </Field>
                <Field label="AWS profile" hint="Optional; overrides keys if set.">
                  <Input value={cfg.aws.profile || ''} onChange={(e) => setPath('aws.profile', e.target.value)} placeholder="default" />
                </Field>
                <Field label="Bedrock bearer token" hint="Optional alternative to AWS keys." className="sm:col-span-2">
                  <SecretInput value={cfg.aws.bearer_token} onChange={(v) => setPath('aws.bearer_token', v)} />
                </Field>
                <div className="sm:col-span-2">
                  <TestResult result={testResult.evaluator} />
                </div>
              </CardBody>
            </Card>
          )}

          {/* Bedrock models */}
          {section === 'bedrock' && (
            <Card>
              <CardHeader
                title="Bedrock models"
                subtitle={modelSource}
                icon={Cpu}
                actions={
                  <Button size="sm" variant="secondary" icon={refreshing ? Loader2 : RefreshCw} onClick={refreshModels} disabled={refreshing}>
                    Refresh from AWS
                  </Button>
                }
              />
              <CardBody className="space-y-5">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                  <Field label="Default model">
                    <Select value={cfg.bedrock.default_model} onChange={(e) => setPath('bedrock.default_model', e.target.value)}>
                      {models.map((m) => (
                        <option key={m.id} value={m.id}>{m.label}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="Max tokens">
                    <Input type="number" value={cfg.bedrock.max_tokens} onChange={(e) => setPath('bedrock.max_tokens', Number(e.target.value))} />
                  </Field>
                  <Field label="Temperature">
                    <Input type="number" step="0.1" value={cfg.bedrock.temperature} onChange={(e) => setPath('bedrock.temperature', Number(e.target.value))} />
                  </Field>
                </div>

                <div>
                  <div className="mb-2 text-xs font-semibold text-slate-600">Enabled models ({enabledIds.length})</div>
                  <div className="space-y-1.5">
                    {models.map((m) => (
                      <label key={m.id} className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-200 px-3 py-2 hover:bg-slate-50">
                        <span className="flex items-center gap-2">
                          <Checkbox checked={enabledIds.includes(m.id)} onChange={() => toggleModel(m.id)} />
                          <span className="text-sm font-medium text-slate-700">{m.label}</span>
                          <span className="font-mono text-[11px] text-slate-400">{m.id}</span>
                        </span>
                        <StatusChip tone="neutral" size="xs">{m.tier || m.note}</StatusChip>
                      </label>
                    ))}
                  </div>
                </div>

                <CustomModelAdder
                  custom={cfg.bedrock.custom_models || []}
                  onAdd={(id) => setPath('bedrock.custom_models', [...(cfg.bedrock.custom_models || []), { id, label: id }])}
                  onRemove={(id) => setPath('bedrock.custom_models', (cfg.bedrock.custom_models || []).filter((c) => c.id !== id))}
                />
              </CardBody>
            </Card>
          )}

          {/* Providers */}
          {section === 'provider' && (
            <div className="space-y-6">
              {Object.entries(cfg.providers).map(([id, p]) => (
                <Card key={id}>
                  <CardHeader
                    title={p.name || id}
                    subtitle={`Adapter: ${p.adapter}`}
                    icon={Boxes}
                    actions={
                      <div className="flex items-center gap-2">
                        <Toggle checked={p.enabled} onChange={(v) => setPath(`providers.${id}.enabled`, v)} label="Enabled" />
                        <Button size="sm" variant="secondary" icon={testing === id ? Loader2 : Plug} onClick={() => runTest(id)} disabled={testing === id}>
                          Test
                        </Button>
                      </div>
                    }
                  />
                  <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <Field label="Adapter type">
                      <Select value={p.adapter} onChange={(e) => setPath(`providers.${id}.adapter`, e.target.value)}>
                        <option value="http">Custom HTTP endpoint</option>
                        <option value="groq">Groq</option>
                        <option value="gemini">Gemini</option>
                        <option value="anthropic">Anthropic</option>
                      </Select>
                    </Field>
                    <Field label="Model" hint="Optional model id for this provider.">
                      <Input value={p.model || ''} onChange={(e) => setPath(`providers.${id}.model`, e.target.value)} className="font-mono text-xs" />
                    </Field>
                    <Field label="API key">
                      <SecretInput value={p.api_key} onChange={(v) => setPath(`providers.${id}.api_key`, v)} />
                    </Field>
                    {p.adapter === 'http' && (
                      <>
                        <Field label="Endpoint URL">
                          <Input value={p.endpoint || ''} onChange={(e) => setPath(`providers.${id}.endpoint`, e.target.value)} className="font-mono text-xs" placeholder="https://api.example.com/v1/chat" />
                        </Field>
                        <Field label="Question path" hint="Dot path where the question is injected.">
                          <Input value={p.question_path || ''} onChange={(e) => setPath(`providers.${id}.question_path`, e.target.value)} className="font-mono text-xs" />
                        </Field>
                        <Field label="Response path" hint="Dot path to the answer text.">
                          <Input value={p.response_path || ''} onChange={(e) => setPath(`providers.${id}.response_path`, e.target.value)} className="font-mono text-xs" />
                        </Field>
                      </>
                    )}
                    <div className="sm:col-span-2">
                      <Toggle checked={p.request_evidence} onChange={(v) => setPath(`providers.${id}.request_evidence`, v)} label="Request evidence links when supported" />
                      <TestResult result={testResult[id]} />
                    </div>
                  </CardBody>
                </Card>
              ))}
            </div>
          )}

          {/* Evaluation criteria (cosmetic / local) */}
          {section === 'eval' && (
            <div className="space-y-6">
              <Card>
                <CardHeader
                  title="Evaluation rubric"
                  subtitle="The engine's source of truth — dimensions, tiers, gates, weighting, and scorers applied to every answer. Read-only."
                  icon={ScanSearch}
                  actions={rubric && <StatusChip tone="neutral" size="xs">config {rubric.weighting?.config_version}</StatusChip>}
                />
                <CardBody>
                  <RubricConfig data={rubric} />
                </CardBody>
              </Card>

              <Card>
                <CardHeader
                  title="Default focus areas"
                  subtitle="Suggested emphasis pre-selected for new runs (does not change the rubric above)."
                  icon={ListChecks}
                />
                <CardBody>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 sm:grid-cols-3">
                    {FOCUS_AREAS.map((f) => (
                      <Checkbox key={f} checked={focus.includes(f)} onChange={() => toggleFocus(f)} label={f} />
                    ))}
                  </div>
                </CardBody>
              </Card>
            </div>
          )}

          {/* Long-term storage (S3) */}
          {section === 's3' && (
            <Card>
              <CardHeader
                title="Long-term storage (S3)"
                subtitle="Store run history in Amazon S3 as the primary record. Uses the AWS credentials from the AWS section; a local copy is always kept as a cache."
                icon={Database}
                actions={
                  <StatusChip tone={cfg.s3?.enabled && cfg.s3?.bucket ? 'success' : 'neutral'} size="xs" dot>
                    {cfg.s3?.enabled && cfg.s3?.bucket ? 'S3 primary' : 'local only'}
                  </StatusChip>
                }
              />
              <CardBody className="space-y-4">
                <Toggle
                  checked={!!cfg.s3?.enabled}
                  onChange={(v) => setPath('s3.enabled', v)}
                  label="Use S3 as the primary run store"
                  description="When on, each saved run is written to S3 and history is read from there."
                />
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <Field label="Bucket" className="md:col-span-2">
                    <Input
                      value={cfg.s3?.bucket || ''}
                      onChange={(e) => setPath('s3.bucket', e.target.value)}
                      placeholder="my-aah-audit-bucket"
                      className="font-mono text-xs"
                    />
                  </Field>
                  <Field label="Region" hint="Blank = use the AWS region.">
                    <Input
                      value={cfg.s3?.region || ''}
                      onChange={(e) => setPath('s3.region', e.target.value)}
                      placeholder={cfg.aws?.region || 'us-east-1'}
                      className="font-mono text-xs"
                    />
                  </Field>
                  <Field label="Key prefix" className="md:col-span-3" hint="Runs are stored under <prefix>/runs/<runId>.json.">
                    <Input
                      value={cfg.s3?.prefix || ''}
                      onChange={(e) => setPath('s3.prefix', e.target.value)}
                      placeholder="aah"
                      className="font-mono text-xs"
                    />
                  </Field>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-500">
                  S3 uses the credentials configured under <span className="font-medium text-slate-600">AWS credentials</span>.
                  If S3 is unreachable, runs still save to the local cache and the app keeps working.
                </div>
              </CardBody>
            </Card>
          )}

          {/* CSV schema (cosmetic / local) */}
          {section === 'csv' && (
            <Card>
              <CardHeader title="CSV export schema" subtitle="Columns included in CSV exports, in order" icon={FileSpreadsheet}
                actions={<StatusChip tone="neutral" size="xs">{csvCols.length} columns</StatusChip>} />
              <CardBody>
                <div className="flex flex-wrap gap-2">
                  {CSV_COLUMNS.map((c) => {
                    const on = csvCols.includes(c)
                    return (
                      <button key={c} onClick={() => toggleCol(c)}
                        className={`focusable rounded-md px-2.5 py-1.5 font-mono text-xs ring-1 ring-inset ${on ? 'bg-brand-50 text-brand-700 ring-brand-300' : 'bg-white text-slate-400 ring-slate-200 line-through'}`}>
                        {c}
                      </button>
                    )
                  })}
                </div>
              </CardBody>
            </Card>
          )}

          {/* Audit (cosmetic / local) */}
          {section === 'audit' && (
            <Card>
              <CardHeader title="Logging & audit settings" icon={ScrollText} />
              <CardBody className="space-y-3">
                <Toggle checked={audit.retainRuns} onChange={(v) => setAudit((a) => ({ ...a, retainRuns: v }))} label="Retain run configuration snapshots" />
                <Toggle checked={audit.logProvider} onChange={(v) => setAudit((a) => ({ ...a, logProvider: v }))} label="Log raw provider responses" />
                <Toggle checked={audit.redactPii} onChange={(v) => setAudit((a) => ({ ...a, redactPii: v }))} label="Redact detected PII in logs" />
                <Toggle checked={audit.verbose} onChange={(v) => setAudit((a) => ({ ...a, verbose: v }))} label="Verbose pipeline logging" />
                <div className="flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5">
                  <span className="text-xs text-rose-800">Clear all draft runs from history</span>
                  <Button size="sm" variant="danger" icon={Trash2}>Clear drafts</Button>
                </div>
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </PageContainer>
  )
}

function CustomModelAdder({ custom, onAdd, onRemove }) {
  const [draft, setDraft] = useState('')
  return (
    <div>
      <div className="mb-2 text-xs font-semibold text-slate-600">Custom model IDs</div>
      <div className="mb-2 flex flex-wrap gap-2">
        {custom.map((c) => (
          <span key={c.id} className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">
            {c.id}
            <button onClick={() => onRemove(c.id)} className="text-slate-400 hover:text-rose-600"><Trash2 className="h-3 w-3" /></button>
          </span>
        ))}
        {!custom.length && <span className="text-xs text-slate-400">None</span>}
      </div>
      <div className="flex items-center gap-2">
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="anthropic.claude-3-5-sonnet-20241022-v2:0" className="font-mono text-xs" />
        <Button size="sm" variant="secondary" icon={Plus} onClick={() => { if (draft.trim()) { onAdd(draft.trim()); setDraft('') } }}>Add</Button>
      </div>
    </div>
  )
}
