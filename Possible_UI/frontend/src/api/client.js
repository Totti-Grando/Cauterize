// ---------------------------------------------------------------------------
// API client seam.
//
// This is the single place to swap the mock layer for your real Python backend.
// Every page/component imports from `./mockApi` via this module's re-exports,
// so flipping USE_MOCK to false (and implementing the fetch calls below) wires
// the whole app to live endpoints without touching any UI code.
// ---------------------------------------------------------------------------

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

// The backend (Agentic_Eval / aah.api.server) is now live, so the app talks to real
// endpoints by default. Set VITE_USE_MOCK=true in the environment to fall back to the
// in-browser mock layer (useful for UI-only work with no server running).
export const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'false') === 'true'

/** Thin fetch wrapper used by real (non-mock) calls. */
export async function request(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`API ${method} ${path} failed: ${res.status} ${detail}`)
  }
  return res.status === 204 ? null : res.json()
}

// Simulated network latency for the mock layer so loading states are visible.
export const mockDelay = (ms = 600) => new Promise((r) => setTimeout(r, ms))

/**
 * POST `body` to `path` and invoke `onEvent(obj)` for each Server-Sent Event as it arrives.
 * Used for the streaming mode flows (manual chat, automatic run). Resolves when the stream
 * closes. EventSource can't POST, so we read the response body stream manually.
 */
export async function streamRequest(path, body, onEvent, { signal } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
    signal,
  })
  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '')
    throw new Error(`stream ${path} failed: ${res.status} ${detail}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const dataLine = frame.split('\n').find((l) => l.startsWith('data:'))
      if (!dataLine) continue
      try {
        onEvent(JSON.parse(dataLine.slice(5).trim()))
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}
