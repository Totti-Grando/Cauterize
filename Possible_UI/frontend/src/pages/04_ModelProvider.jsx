import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Cpu, Boxes, SlidersHorizontal, ArrowRight, KeyRound, Loader2, Check, ShieldCheck, ShieldAlert } from 'lucide-react'
import { PageContainer, PageHeader } from '../components/layout/AppLayout'
import Stepper from '../components/Stepper'
import { Card, CardHeader, CardBody } from '../components/Card'
import Button from '../components/Button'
import ModelCard from '../components/ModelCard'
import ProviderCard from '../components/ProviderCard'
import StatusChip from '../components/StatusChip'
import { Toggle, Field, Input, Select, Checkbox, Modal, Disclosure } from '../components/ui'
import { api } from '../api'
import { useRun } from '../context/RunContext'

const AWS_REGIONS = ['us-east-1', 'us-west-2', 'eu-west-1', 'eu-central-1', 'ap-southeast-1']

export default function ModelProvider() {
  const navigate = useNavigate()
  const { run, update } = useRun()
  const [models, setModels] = useState([])
  const [providers, setProviders] = useState([])
  const [aws, setAws] = useState(null)
  const [model, setModel] = useState(run.primaryModel ?? 'anthropic.claude-sonnet')
  const [provider, setProvider] = useState(run.provider ?? 'ravenpack')
  const [modelId, setModelId] = useState(run.customModelId ?? '')
  const [useGen, setUseGen] = useState(run.useForGeneration)
  const [useEval, setUseEval] = useState(run.useForEvaluation)
  const [settings, setSettings] = useState({
    questionCount: run.questionCount,
    recursiveRounds: run.recursiveRounds,
    strategyProbing: run.strategyProbing,
    groundednessChecks: run.groundednessChecks,
    shortfallClassification: run.shortfallClassification,
  })

  const [cred, setCred] = useState(null) // active credential modal descriptor
  const [saving, setSaving] = useState(false)

  const refreshProviders = () => api.getProviders().then(setProviders)
  const refreshAws = () => api.getAwsStatus().then(setAws)

  useEffect(() => {
    api.getModels().then(setModels)
    refreshProviders()
    refreshAws()
  }, [])

  const providerById = (id) => providers.find((p) => p.id === id)

  // --- credential prompts -------------------------------------------------------
  const openProviderModal = (p) => {
    const req = p.requiredCredentials || []
    const fields = req.map((key) => ({
      key,
      label: p.credentialFields?.[key]?.label ?? key,
      secret: p.credentialFields?.[key]?.secret ?? true,
      placeholder: p.credentialFields?.[key]?.placeholder ?? '',
      configured: p.credentialsStatus?.[key] ?? false,
      mono: key === 'endpoint' || key === 'api_key',
    }))
    setCred({
      kind: 'provider',
      id: p.id,
      title: `Configure ${p.name}`,
      description: `${p.name} needs the following before it can be used. Secrets are stored on the server and never shown again.`,
      fields,
      initial: {},
    })
  }

  const openAwsModal = () => {
    setCred({
      kind: 'aws',
      title: 'Configure AWS for Bedrock',
      description: 'Bedrock models run through your AWS account. Enter keys, or leave blank to use an AWS profile / IAM role configured in Settings.',
      fields: [
        { key: 'region', label: 'AWS region', type: 'select', options: AWS_REGIONS },
        { key: 'access_key_id', label: 'Access key ID', secret: true, configured: aws?.hasKeys, mono: true },
        { key: 'secret_access_key', label: 'Secret access key', secret: true, configured: aws?.hasKeys, mono: true },
      ],
      initial: { region: aws?.region || 'us-east-1' },
    })
  }

  const onSelectProvider = (id) => {
    setProvider(id)
    const p = providerById(id)
    if (p && !p.configured) openProviderModal(p)
  }

  const onSelectModel = (id) => {
    setModel(id)
    if (aws && !aws.configured) openAwsModal()
  }

  const saveCred = async (vals) => {
    const filled = Object.fromEntries(
      Object.entries(vals).filter(([, v]) => typeof v === 'string' && v.trim() !== ''),
    )
    setSaving(true)
    if (cred.kind === 'provider') {
      await api.saveSettings({ providers: { [cred.id]: { ...filled, enabled: true } } })
      await refreshProviders()
    } else {
      await api.saveSettings({ aws: { region: vals.region || aws?.region || 'us-east-1', ...filled }, evaluator: { backend: 'bedrock' } })
      await refreshAws()
    }
    setSaving(false)
    setCred(null)
  }

  const cont = () => {
    update({
      primaryModel: model,
      customModelId: modelId,
      provider,
      useForGeneration: useGen,
      useForEvaluation: useEval,
      ...settings,
      status: 'Configuring',
    })
    navigate('/qa-mode')
  }

  const selProvider = providerById(provider)

  return (
    <PageContainer>
      <PageHeader
        title="Models & Providers"
        description="Pick the Bedrock model that evaluates and the provider you want to test."
        actions={
          <Button onClick={cont} iconRight={ArrowRight}>
            Continue to Q&A Mode
          </Button>
        }
      />
      <Card className="mb-6 px-6 py-4">
        <Stepper current={1} />
      </Card>

      <div className="space-y-6">
        {/* Section 1 — primary model */}
        <Card>
          <CardHeader
            eyebrow="Section 1"
            title="Primary Evaluation Model"
            subtitle="An Amazon Bedrock chat model used for Q&A generation and/or evaluation."
            icon={Cpu}
            actions={
              aws && (
                <button
                  onClick={openAwsModal}
                  className="focusable inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium hover:bg-slate-50"
                >
                  {aws.configured ? (
                    <StatusChip tone="success" size="xs" dot><ShieldCheck className="mr-1 h-3 w-3" />AWS configured</StatusChip>
                  ) : (
                    <StatusChip tone="warning" size="xs" dot><ShieldAlert className="mr-1 h-3 w-3" />Configure AWS</StatusChip>
                  )}
                </button>
              )
            }
          />
          <CardBody className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div>
              <div className="mb-2 text-xs font-semibold text-slate-600">Select Bedrock chat model</div>
              <div className="space-y-2">
                {models.map((m) => (
                  <ModelCard key={m.id} model={m} selected={model === m.id} onSelect={() => onSelectModel(m.id)} />
                ))}
              </div>
            </div>
            <div className="space-y-4">
              <Field label="Model ID (advanced)" hint="Overrides the friendly name when targeting a specific Bedrock model.">
                <Input value={modelId} onChange={(e) => setModelId(e.target.value)} placeholder="anthropic.claude-3-5-sonnet-20241022-v2:0" className="font-mono text-xs" />
              </Field>
              <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                <Toggle checked={useGen} onChange={setUseGen} label="Use this model for Q&A generation" />
                <Toggle checked={useEval} onChange={setUseEval} label="Use this model for evaluation" />
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Section 2 — secondary provider */}
        <Card>
          <CardHeader
            eyebrow="Section 2"
            title="Secondary Provider to Test"
            subtitle="The chatbot or research provider whose answers will be questioned and evaluated."
            icon={Boxes}
            actions={
              selProvider && (
                <Button size="sm" variant="secondary" icon={KeyRound} onClick={() => openProviderModal(selProvider)}>
                  {selProvider.configured ? 'Edit credentials' : 'Add credentials'}
                </Button>
              )
            }
          />
          <CardBody>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {providers.map((p) => (
                <ProviderCard
                  key={p.id}
                  provider={p}
                  selected={provider === p.id}
                  onSelect={() => onSelectProvider(p.id)}
                  configured={p.requiredCredentials?.length ? p.configured : null}
                />
              ))}
            </div>
            {selProvider && !selProvider.configured && (
              <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-800">
                <ShieldAlert className="h-4 w-4 shrink-0" />
                {selProvider.name} needs {selProvider.missingCredentials?.map((c) => c.replace(/_/g, ' ')).join(' + ')} before you can run against it.
                <button onClick={() => openProviderModal(selProvider)} className="ml-auto font-semibold underline">Configure now</button>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Section 3 — evaluation settings (collapsed; sensible defaults shown in the summary) */}
        <Disclosure
          icon={SlidersHorizontal}
          title="Advanced evaluation settings"
          summary={`${settings.questionCount} questions · ${settings.recursiveRounds} round${settings.recursiveRounds > 1 ? 's' : ''} · ${
            [settings.strategyProbing, settings.groundednessChecks, settings.shortfallClassification].filter(Boolean).length
          }/3 checks on`}
        >
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-4">
              <Field label="Number of questions">
                <Select value={settings.questionCount} onChange={(e) => setSettings((s) => ({ ...s, questionCount: Number(e.target.value) }))}>
                  {[3, 5, 8, 10, 15, 20].map((n) => (
                    <option key={n} value={n}>{n} questions</option>
                  ))}
                </Select>
              </Field>
              <Field label="Number of recursive rounds" hint="Follow-up probing rounds per question.">
                <Select value={settings.recursiveRounds} onChange={(e) => setSettings((s) => ({ ...s, recursiveRounds: Number(e.target.value) }))}>
                  {[1, 2, 3].map((n) => (
                    <option key={n} value={n}>{n} round{n > 1 ? 's' : ''}</option>
                  ))}
                </Select>
              </Field>
            </div>
            <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
              <Checkbox checked={settings.strategyProbing} onChange={(v) => setSettings((s) => ({ ...s, strategyProbing: v }))} label="Enable strategy-based probing" />
              <Checkbox checked={settings.groundednessChecks} onChange={(v) => setSettings((s) => ({ ...s, groundednessChecks: v }))} label="Enable link / source groundedness checks" />
              <Checkbox checked={settings.shortfallClassification} onChange={(v) => setSettings((s) => ({ ...s, shortfallClassification: v }))} label="Enable shortfall classification" />
            </div>
          </div>
        </Disclosure>
      </div>

      <CredentialModal cred={cred} saving={saving} onClose={() => setCred(null)} onSave={saveCred} />
    </PageContainer>
  )
}

function CredentialModal({ cred, saving, onClose, onSave }) {
  const [vals, setVals] = useState({})
  useEffect(() => {
    setVals(cred?.initial ?? {})
  }, [cred])
  if (!cred) return null
  const set = (k, v) => setVals((s) => ({ ...s, [k]: v }))

  return (
    <Modal
      open={!!cred}
      onClose={onClose}
      title={cred.title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button icon={saving ? Loader2 : Check} onClick={() => onSave(vals)} disabled={saving}>
            {saving ? 'Saving…' : 'Save & continue'}
          </Button>
        </>
      }
    >
      {cred.description && <p className="mb-4 text-xs leading-relaxed text-slate-500">{cred.description}</p>}
      <div className="space-y-4">
        {cred.fields.map((f) => (
          <Field key={f.key} label={f.label} hint={f.configured ? 'Already set — leave blank to keep the stored value.' : f.hint}>
            {f.type === 'select' ? (
              <Select value={vals[f.key] ?? ''} onChange={(e) => set(f.key, e.target.value)}>
                {f.options.map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </Select>
            ) : (
              <Input
                type={f.secret ? 'password' : 'text'}
                value={vals[f.key] ?? ''}
                placeholder={f.configured ? '•••• already set' : f.placeholder || ''}
                onChange={(e) => set(f.key, e.target.value)}
                className={f.mono ? 'font-mono text-xs' : ''}
              />
            )}
          </Field>
        ))}
      </div>
    </Modal>
  )
}
