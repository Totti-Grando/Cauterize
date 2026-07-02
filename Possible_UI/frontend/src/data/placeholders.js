// Realistic placeholder data for Q&A Evaluation Studio.
// Banking / financial-research assistant evaluation context.
// NO real customer data — illustrative content only.

export const BEDROCK_MODELS = [
  { id: 'anthropic.claude-sonnet', label: 'Claude Sonnet', note: 'Balanced reasoning · recommended', tier: 'Balanced' },
  { id: 'anthropic.claude-haiku', label: 'Claude Haiku', note: 'Fast · lower cost', tier: 'Fast' },
  { id: 'anthropic.claude-opus', label: 'Claude Opus', note: 'Deepest reasoning', tier: 'Deep' },
  { id: 'amazon.titan-text', label: 'Titan Text', note: 'Amazon foundation model', tier: 'General' },
  { id: 'custom', label: 'Custom Bedrock Model ID', note: 'Bring your own model id', tier: 'Custom' },
]

export const PROVIDERS = [
  {
    id: 'ravenpack',
    name: 'RavenPack',
    description: 'News & document analytics provider with entity-level sentiment and event detection.',
    outputType: 'Structured analytics + narrative',
    linkSupport: true,
    evidenceSupport: true,
    accent: 'brand',
  },
  {
    id: 'nexa',
    name: 'Nexa',
    description: 'Research-grounded assistant for market and issuer-level questions.',
    outputType: 'Narrative answer with citations',
    linkSupport: true,
    evidenceSupport: true,
    accent: 'violet',
  },
  {
    id: 'custom',
    name: 'Custom Provider',
    description: 'Connect any chatbot or research API via a custom endpoint definition.',
    outputType: 'Configurable',
    linkSupport: false,
    evidenceSupport: false,
    accent: 'slate',
  },
]

export const QA_MODES = [
  {
    id: 'manual',
    title: 'You control everything',
    name: 'Manual Mode',
    description:
      'Write or paste your own questions. The system sends them to the secondary provider and evaluates the answers.',
    icon: 'PencilLine',
  },
  {
    id: 'assisted',
    title: 'Suggested but still in your power',
    name: 'Assisted Mode',
    description:
      'The system suggests Q&A pairs. You review, edit, approve, reject, or regenerate before running.',
    icon: 'Sparkles',
  },
  {
    id: 'automatic',
    title: 'Fully automatic — watch the program run',
    name: 'Fully Automatic Mode',
    description:
      'The system generates questions, queries the selected provider, evaluates the outputs, and produces a full results report.',
    icon: 'Workflow',
  },
]

export const FOCUS_AREAS = [
  'Accuracy',
  'Groundedness',
  'Completeness',
  'Hallucination resistance',
  'Missing information',
  'Reasoning quality',
  'Source quality',
  'Contradiction detection',
]

export const SAMPLE_DOCUMENTS = [
  { id: 'd1', name: 'Q3_Issuer_Briefing.pdf', type: 'PDF', size: '2.4 MB', status: 'extracted' },
  { id: 'd2', name: 'Reputational_Risk_Memo.docx', type: 'DOCX', size: '684 KB', status: 'extracted' },
  { id: 'd3', name: 'Regulatory_Notes.txt', type: 'TXT', size: '38 KB', status: 'review' },
]

export const SAMPLE_LINKS = [
  {
    id: 'l1',
    url: 'https://research.example.com/issuer/esg-controversy-aug',
    sourceType: 'Research article',
    fetchStatus: 'success',
    extractStatus: 'extracted',
  },
  {
    id: 'l2',
    url: 'https://newswire.example.com/2026/regulatory-inquiry',
    sourceType: 'Newswire',
    fetchStatus: 'success',
    extractStatus: 'extracted',
  },
  {
    id: 'l3',
    url: 'https://portal.example.com/secure/filings',
    sourceType: 'SharePoint',
    fetchStatus: 'login',
    extractStatus: 'blocked',
  },
]

export const SOURCE_QUALITY = [
  { label: 'Extractable text', count: 4, tone: 'success' },
  { label: 'Login page detected', count: 1, tone: 'warning' },
  { label: 'Empty source', count: 0, tone: 'neutral' },
  { label: 'Needs review', count: 1, tone: 'warning' },
]

// The hero sample question referenced throughout the spec.
export const SAMPLE_QUESTION_TEXT =
  'Over the last 30 days, what source-grounded evidence suggests increased reputational risk for the selected issuer?'

export const PERSONAS = ['Risk Analyst', 'Compliance Officer', 'Portfolio Manager', 'Research Lead']
export const CATEGORIES = ['Reputational risk', 'Regulatory', 'Market sentiment', 'ESG', 'Liquidity']
export const DIFFICULTIES = ['Easy', 'Medium', 'Hard']

export const SAMPLE_PROPOSED_QUESTIONS = [
  {
    id: 'Q-001',
    persona: 'Risk Analyst',
    category: 'Reputational risk',
    difficulty: 'Hard',
    focus: ['Groundedness', 'Missing information'],
    text: SAMPLE_QUESTION_TEXT,
    why: 'Tests whether the provider can tie a risk claim to dated, source-grounded evidence rather than general sentiment.',
    expected:
      'A grounded answer cites at least two usable sources from the last 30 days describing specific reputational events, and flags the login-blocked filing as unavailable.',
    status: 'pending',
  },
  {
    id: 'Q-002',
    persona: 'Compliance Officer',
    category: 'Regulatory',
    difficulty: 'Medium',
    focus: ['Accuracy', 'Source quality'],
    text: 'Which regulatory inquiries referenced in the provided sources are still open, and what is their stated scope?',
    why: 'Checks extraction of regulatory status from documents vs. fabricated detail.',
    expected: 'Lists only inquiries present in sources, with scope quoted or paraphrased and dates attributed.',
    status: 'approved',
  },
  {
    id: 'Q-003',
    persona: 'Portfolio Manager',
    category: 'Market sentiment',
    difficulty: 'Easy',
    focus: ['Completeness', 'Contradiction detection'],
    text: 'Summarize the net sentiment trend for the issuer over the briefing period and note any contradictory signals.',
    why: 'Surfaces whether the provider reconciles conflicting signals or cherry-picks.',
    expected: 'Gives a directional trend with at least one supporting datapoint and explicitly names contradictions.',
    status: 'pending',
  },
  {
    id: 'Q-004',
    persona: 'Research Lead',
    category: 'ESG',
    difficulty: 'Hard',
    focus: ['Hallucination resistance', 'Reasoning quality'],
    text: 'Does the ESG controversy described in the August article materially change the issuer risk profile? Justify.',
    why: 'Probes reasoning quality and resistance to overclaiming materiality.',
    expected: 'Reasoned judgment grounded in the article, avoiding unsupported materiality conclusions.',
    status: 'edited',
  },
  {
    id: 'Q-005',
    persona: 'Risk Analyst',
    category: 'Liquidity',
    difficulty: 'Medium',
    focus: ['Accuracy', 'Missing information'],
    text: 'What liquidity indicators are available in the sources, and which expected indicators are missing?',
    why: 'Tests explicit acknowledgment of missing information.',
    expected: 'Reports available indicators and names the gaps rather than inferring them.',
    status: 'rejected',
  },
]

export const VERDICTS = {
  correct: { label: 'Correct', tone: 'success' },
  partial: { label: 'Partial', tone: 'warning' },
  incorrect: { label: 'Incorrect', tone: 'danger' },
  unverifiable: { label: 'Unverifiable', tone: 'info' },
}

export const SHORTFALL_TAGS = [
  'missing_information',
  'not_grounded_in_context',
  'unsupported_claim',
  'contradiction',
  'overclaimed_materiality',
  'stale_source',
]

// The hero evaluation result used across Workspace / Results / Evidence.
export const SAMPLE_EVALUATIONS = [
  {
    id: 'E-001',
    questionId: 'Q-001',
    question: SAMPLE_QUESTION_TEXT,
    provider: 'RavenPack',
    providerAnswer:
      'Over the trailing 30 days, sentiment for the issuer declined modestly, driven by an ESG controversy reported in early August and a regulatory inquiry disclosed mid-month. Coverage volume rose ~18% with a negative skew. A filing portal was referenced but could not be retrieved.',
    expectedAnswer:
      'A grounded answer cites at least two usable sources from the last 30 days describing specific reputational events, and flags the login-blocked filing as unavailable.',
    verdict: 'partial',
    grounded: false,
    sourceGroundedness: 'partial',
    reasoningQuality: 'Adequate',
    shortfalls: ['missing_information', 'not_grounded_in_context'],
    missingPoints: ['No date attribution for the 18% coverage figure', 'Regulatory inquiry scope not stated'],
    incorrectPoints: ['Implies materiality not supported by the cited sources'],
    extraPoints: ['Coverage-volume statistic not requested but relevant'],
    finalSummary:
      'The answer correctly identifies two reputational drivers but does not ground the quantitative claim and omits the inquiry scope. Login-blocked source was acknowledged. Net: partial — usable with human verification.',
    evidence: [
      {
        id: 'ev1',
        title: 'ESG controversy resurfaces for issuer',
        domain: 'research.example.com',
        support: 'partial',
        quote:
          'Analysts flagged renewed scrutiny over the issuer’s supply-chain disclosures following an August report.',
        author: 'J. Marchetti',
        published: '2026-08-04',
        canonicalUrl: 'https://research.example.com/issuer/esg-controversy-aug',
        sourceUrl: 'https://research.example.com/issuer/esg-controversy-aug',
        fetchSuccess: true,
        textLength: 8421,
      },
      {
        id: 'ev2',
        title: 'Regulator opens inquiry into disclosures',
        domain: 'newswire.example.com',
        support: 'strong',
        quote: 'A regulator confirmed an inquiry into the issuer’s recent disclosures was opened this month.',
        author: 'Newswire Staff',
        published: '2026-08-15',
        canonicalUrl: 'https://newswire.example.com/2026/regulatory-inquiry',
        sourceUrl: 'https://newswire.example.com/2026/regulatory-inquiry',
        fetchSuccess: true,
        textLength: 5210,
      },
      {
        id: 'ev3',
        title: 'Secure filings portal',
        domain: 'portal.example.com',
        support: 'not_evaluable',
        quote: '',
        author: null,
        published: null,
        canonicalUrl: 'https://portal.example.com/secure/filings',
        sourceUrl: 'https://portal.example.com/secure/filings',
        fetchSuccess: false,
        textLength: 0,
      },
    ],
  },
  {
    id: 'E-002',
    questionId: 'Q-002',
    question: 'Which regulatory inquiries referenced in the provided sources are still open, and what is their stated scope?',
    provider: 'RavenPack',
    providerAnswer:
      'One regulatory inquiry was disclosed mid-month and remains open. Its scope concerns recent issuer disclosures; no resolution date was provided.',
    expectedAnswer: 'Lists only inquiries present in sources, with scope quoted or paraphrased and dates attributed.',
    verdict: 'correct',
    grounded: true,
    sourceGroundedness: 'grounded',
    reasoningQuality: 'Strong',
    shortfalls: [],
    missingPoints: [],
    incorrectPoints: [],
    extraPoints: [],
    finalSummary: 'Accurate and grounded. The single open inquiry is correctly attributed with stated scope and date.',
    evidence: [
      {
        id: 'ev2',
        title: 'Regulator opens inquiry into disclosures',
        domain: 'newswire.example.com',
        support: 'strong',
        quote: 'A regulator confirmed an inquiry into the issuer’s recent disclosures was opened this month.',
        author: 'Newswire Staff',
        published: '2026-08-15',
        canonicalUrl: 'https://newswire.example.com/2026/regulatory-inquiry',
        sourceUrl: 'https://newswire.example.com/2026/regulatory-inquiry',
        fetchSuccess: true,
        textLength: 5210,
      },
    ],
  },
  {
    id: 'E-003',
    questionId: 'Q-003',
    question: 'Summarize the net sentiment trend for the issuer over the briefing period and note any contradictory signals.',
    provider: 'RavenPack',
    providerAnswer:
      'Net sentiment trended negative overall, though a mid-period product announcement briefly lifted sentiment before coverage normalized.',
    expectedAnswer: 'Gives a directional trend with at least one supporting datapoint and explicitly names contradictions.',
    verdict: 'partial',
    grounded: true,
    sourceGroundedness: 'partial',
    reasoningQuality: 'Adequate',
    shortfalls: ['missing_information'],
    missingPoints: ['No quantitative datapoint cited for the trend direction'],
    incorrectPoints: [],
    extraPoints: [],
    finalSummary: 'Directionally grounded and names a contradictory signal, but lacks a supporting datapoint. Partial.',
    evidence: [],
  },
  {
    id: 'E-004',
    questionId: 'Q-004',
    question: 'Does the ESG controversy described in the August article materially change the issuer risk profile? Justify.',
    provider: 'RavenPack',
    providerAnswer:
      'Yes — the controversy materially increases the risk profile and should trigger a rating review.',
    expectedAnswer: 'Reasoned judgment grounded in the article, avoiding unsupported materiality conclusions.',
    verdict: 'incorrect',
    grounded: false,
    sourceGroundedness: 'ungrounded',
    reasoningQuality: 'Weak',
    shortfalls: ['overclaimed_materiality', 'unsupported_claim', 'not_grounded_in_context'],
    missingPoints: ['No basis in source for a rating-review conclusion'],
    incorrectPoints: ['Asserts materiality the source does not support'],
    extraPoints: ['Introduces a rating-review recommendation not requested'],
    finalSummary:
      'Overclaims materiality and recommends action unsupported by the cited article. Incorrect — flag for reviewer.',
    evidence: [
      {
        id: 'ev1',
        title: 'ESG controversy resurfaces for issuer',
        domain: 'research.example.com',
        support: 'weak',
        quote: 'Analysts flagged renewed scrutiny over the issuer’s supply-chain disclosures.',
        author: 'J. Marchetti',
        published: '2026-08-04',
        canonicalUrl: 'https://research.example.com/issuer/esg-controversy-aug',
        sourceUrl: 'https://research.example.com/issuer/esg-controversy-aug',
        fetchSuccess: true,
        textLength: 8421,
      },
    ],
  },
  {
    id: 'E-005',
    questionId: 'Q-005',
    question: 'What liquidity indicators are available in the sources, and which expected indicators are missing?',
    provider: 'RavenPack',
    providerAnswer:
      'The sources do not contain liquidity indicators. Expected indicators such as bid-ask spreads and turnover are not present.',
    expectedAnswer: 'Reports available indicators and names the gaps rather than inferring them.',
    verdict: 'unverifiable',
    grounded: true,
    sourceGroundedness: 'partial',
    reasoningQuality: 'Adequate',
    shortfalls: ['missing_information'],
    missingPoints: [],
    incorrectPoints: [],
    extraPoints: [],
    finalSummary:
      'Correctly reports the absence of liquidity data, but the claim cannot be fully verified against blocked sources. Unverifiable.',
    evidence: [],
  },
]

export const RUN_HISTORY = [
  {
    runId: 'RUN-2026-0612-A',
    date: '2026-06-12 14:22',
    user: 'p.intraligi',
    documents: 3,
    links: 3,
    primaryModel: 'Claude Sonnet',
    provider: 'RavenPack',
    mode: 'Assisted',
    questions: 5,
    verdictSummary: { correct: 1, partial: 2, incorrect: 1, unverifiable: 1 },
    exportStatus: 'exported',
    notes: 'Reputational-risk sweep for issuer briefing. Login-blocked filing excluded.',
  },
  {
    runId: 'RUN-2026-0610-B',
    date: '2026-06-10 09:05',
    user: 'p.intraligi',
    documents: 2,
    links: 1,
    primaryModel: 'Claude Opus',
    provider: 'Nexa',
    mode: 'Automatic',
    questions: 8,
    verdictSummary: { correct: 5, partial: 2, incorrect: 0, unverifiable: 1 },
    exportStatus: 'pending',
    notes: 'Regulatory follow-up. Strong groundedness overall.',
  },
  {
    runId: 'RUN-2026-0605-C',
    date: '2026-06-05 16:48',
    user: 'a.okafor',
    documents: 5,
    links: 0,
    primaryModel: 'Claude Haiku',
    provider: 'RavenPack',
    mode: 'Manual',
    questions: 4,
    verdictSummary: { correct: 2, partial: 1, incorrect: 1, unverifiable: 0 },
    exportStatus: 'draft',
    notes: 'Draft — pending reviewer sign-off.',
  },
]

export const RUN_LOG_STEPS = [
  { step: 'Reading sources', status: 'done', message: '5 sources queued, 4 readable' },
  { step: 'Extracting text', status: 'done', message: '4 documents extracted, 1 login page detected' },
  { step: 'Generating questions', status: 'done', message: '5 questions generated across 4 personas' },
  { step: 'Querying secondary provider', status: 'active', message: 'RavenPack — 3 of 5 answered' },
  { step: 'Extracting links', status: 'pending', message: 'Awaiting answers' },
  { step: 'Evaluating groundedness', status: 'pending', message: 'Awaiting answers' },
  { step: 'Classifying shortfalls', status: 'pending', message: 'Awaiting evaluation' },
  { step: 'Writing results', status: 'pending', message: 'Awaiting evaluation' },
]

export const RUN_LOG_LINES = [
  { ts: '14:22:01', step: 'Reading sources', status: 'info', message: 'Queued 5 sources (3 docs, 3 links — 1 duplicate skipped)' },
  { ts: '14:22:03', step: 'Extracting text', status: 'success', message: 'Q3_Issuer_Briefing.pdf extracted (8,421 chars)' },
  { ts: '14:22:04', step: 'Extracting text', status: 'warning', message: 'portal.example.com returned a login page — skipped' },
  { ts: '14:22:09', step: 'Generating questions', status: 'success', message: 'Generated 5 questions (1 hard, 2 medium, 2 easy)' },
  { ts: '14:22:14', step: 'Querying provider', status: 'info', message: 'RavenPack: sent Q-001' },
  { ts: '14:22:18', step: 'Querying provider', status: 'success', message: 'RavenPack: Q-001 answered (1,204 chars)' },
  { ts: '14:22:22', step: 'Querying provider', status: 'warning', message: 'Q-004 answer flagged: possible overclaim' },
]

export const AUTO_METRICS = [
  { label: 'Questions generated', value: 5, tone: 'neutral' },
  { label: 'Answers received', value: 3, tone: 'neutral' },
  { label: 'Evaluations completed', value: 2, tone: 'neutral' },
  { label: 'Unsupported claims found', value: 2, tone: 'danger' },
  { label: 'Unverifiable answers', value: 1, tone: 'info' },
  { label: 'Sources extracted', value: 4, tone: 'success' },
  { label: 'Links failed', value: 1, tone: 'warning' },
]
