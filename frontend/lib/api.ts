import type { AskResponse } from './types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export async function askQuestion(
  question: string,
  history: { question: string; answer: string }[]
): Promise<AskResponse> {
  const response = await fetch(`${API_URL}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history }),
  })
  if (!response.ok) {
    let detail: string | undefined
    try {
      const body = await response.json()
      detail = typeof body?.detail === 'string' ? body.detail : undefined
    } catch {
      // Response body wasn't JSON (or had no body) — fall back below.
    }
    throw new Error(detail || `Ask request failed: ${response.status}`)
  }
  return response.json()
}
