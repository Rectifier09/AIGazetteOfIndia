import type { QACardData } from './types'

const STORAGE_KEY = 'egazette_history'
const MAX_EXCHANGES = 50
const MAX_AGE_DAYS = 30

export function loadHistory(): QACardData[] {
  const raw = localStorage.getItem(STORAGE_KEY)
  const savedAt = Number(localStorage.getItem(`${STORAGE_KEY}_savedAt`) || 0)
  const ageMs = Date.now() - savedAt
  if (!raw || (savedAt > 0 && ageMs > MAX_AGE_DAYS * 24 * 60 * 60 * 1000)) return []
  let cards: QACardData[]
  try {
    cards = JSON.parse(raw)
  } catch {
    clearHistory()
    return []
  }
  if (!Array.isArray(cards)) {
    clearHistory()
    return []
  }
  return cards.map((c) => ({ ...c, isHistorical: true }))
}

export function saveHistory(cards: QACardData[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cards.slice(-MAX_EXCHANGES)))
    localStorage.setItem(`${STORAGE_KEY}_savedAt`, String(Date.now()))
  } catch {
    // Storage quota exceeded or unavailable — history persistence is a
    // best-effort convenience, not required for the app to function.
  }
}

export function clearHistory(): void {
  localStorage.removeItem(STORAGE_KEY)
  localStorage.removeItem(`${STORAGE_KEY}_savedAt`)
}

export function getSessionDividerLabel(): string {
  const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })
  return `New session · ${today}`
}
