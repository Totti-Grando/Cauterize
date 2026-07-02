// Central mapping from domain values -> chip tones + labels.
// Keeps verdict/groundedness/support styling consistent everywhere.

export function verdictTone(v) {
  return { correct: 'success', partial: 'warning', incorrect: 'danger', unverifiable: 'info' }[v] ?? 'neutral'
}
export function verdictLabel(v) {
  return { correct: 'Correct', partial: 'Partial', incorrect: 'Incorrect', unverifiable: 'Unverifiable' }[v] ?? v
}

export function groundedTone(g) {
  return { grounded: 'success', partial: 'warning', ungrounded: 'danger' }[g] ?? 'neutral'
}
export function groundedLabel(g) {
  return { grounded: 'Grounded', partial: 'Partial', ungrounded: 'Ungrounded' }[g] ?? g
}

export function supportTone(s) {
  return {
    strong: 'success',
    partial: 'warning',
    weak: 'warning',
    unsupported: 'danger',
    not_evaluable: 'neutral',
  }[s] ?? 'neutral'
}
export function supportLabel(s) {
  return {
    strong: 'Strong support',
    partial: 'Partial support',
    weak: 'Weak support',
    unsupported: 'Unsupported',
    not_evaluable: 'Not evaluable',
  }[s] ?? s
}

// Shortfall tags render as small rose/amber chips.
export function shortfallTone(tag) {
  const danger = ['unsupported_claim', 'not_grounded_in_context', 'contradiction', 'overclaimed_materiality']
  return danger.includes(tag) ? 'danger' : 'warning'
}
export function prettyTag(tag) {
  return tag.replace(/_/g, ' ')
}
