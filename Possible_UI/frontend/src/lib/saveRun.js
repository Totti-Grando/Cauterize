import { api } from '../api'

const MODE_LABEL = { manual: 'Manual', assisted: 'Assisted', automatic: 'Automatic' }

/**
 * Build a run-history record from the current chat transcript + run configuration and
 * persist it via the API. Returns the saved record, or null if there is nothing to save.
 */
export async function saveRunFrom(run, summary, turns) {
  const evaluations = turns.map((t) => t.evaluation).filter(Boolean)
  if (!evaluations.length) return null
  return api.saveRun({
    mode: MODE_LABEL[run.mode] || 'Manual',
    provider: summary.providerLabel,
    primaryModel: summary.primaryModelLabel,
    documents: summary.documents,
    links: summary.links,
    evaluations,
  })
}
