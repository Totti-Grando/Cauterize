import { createContext, useContext, useMemo, useState } from 'react'

// Shared state for the current evaluation "story" — flows across the wizard
// pages (Sources -> Models -> Q&A Mode -> Run -> Review -> Export).

const RunContext = createContext(null)

const INITIAL = {
  status: 'Draft', // Draft | Configuring | Ready | Running | Paused | Complete
  termsAccepted: false,
  documents: [],
  links: [],
  primaryModel: null, // model id
  customModelId: '',
  useForGeneration: true,
  useForEvaluation: true,
  provider: null, // provider id
  mode: null, // manual | assisted | automatic
  objective: 'learning', // learning | attack — how Layer B lessons are used
  questionCount: 5,
  recursiveRounds: 1,
  difficultyMix: 'Balanced',
  focusAreas: ['Accuracy', 'Groundedness', 'Hallucination resistance'],
  strategyProbing: true,
  groundednessChecks: true,
  shortfallClassification: true,
  round: 1,
}

export function RunProvider({ children }) {
  const [run, setRun] = useState(INITIAL)

  const value = useMemo(() => {
    const update = (patch) => setRun((prev) => ({ ...prev, ...patch }))
    const reset = () => setRun(INITIAL)

    // Derived counts shown in the status bar / summary panels.
    const summary = {
      documents: run.documents.length || 3,
      links: run.links.length || 3,
      primaryModelLabel: run.primaryModel ? labelForModel(run.primaryModel) : 'Not selected',
      providerLabel: run.provider ? labelForProvider(run.provider) : 'Not selected',
      modeLabel: run.mode ? labelForMode(run.mode) : 'Not selected',
    }

    return { run, update, reset, summary }
  }, [run])

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>
}

export function useRun() {
  const ctx = useContext(RunContext)
  if (!ctx) throw new Error('useRun must be used within RunProvider')
  return ctx
}

// --- small label helpers (kept here to avoid importing data into context) ---
function labelForModel(id) {
  const map = {
    'anthropic.claude-sonnet': 'Bedrock Claude Sonnet',
    'anthropic.claude-haiku': 'Bedrock Claude Haiku',
    'anthropic.claude-opus': 'Bedrock Claude Opus',
    'amazon.titan-text': 'Titan Text',
    custom: 'Custom Bedrock Model',
  }
  return map[id] ?? id
}
function labelForProvider(id) {
  const map = { ravenpack: 'RavenPack', nexa: 'Nexa', custom: 'Custom Provider' }
  return map[id] ?? id
}
function labelForMode(id) {
  const map = { manual: 'Manual Mode', assisted: 'Assisted Mode', automatic: 'Fully Automatic Mode' }
  return map[id] ?? id
}
