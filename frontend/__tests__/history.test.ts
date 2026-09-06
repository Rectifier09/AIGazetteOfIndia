import { loadHistory, saveHistory, clearHistory, getSessionDividerLabel } from '@/lib/history'
import type { QACardData } from '@/lib/types'

const card = (id: string, isHistorical = false): QACardData => ({
  id, question: `Q${id}`, status: 'answered', answer: 'A', citations: [], disclaimer: 'd', isHistorical,
})

describe('history persistence', () => {
  beforeEach(() => localStorage.clear())

  it('returns an empty array when nothing is stored', () => {
    expect(loadHistory()).toEqual([])
  })

  it('round-trips saved cards and marks them historical on load', () => {
    saveHistory([card('1'), card('2')])
    const loaded = loadHistory()
    expect(loaded).toHaveLength(2)
    expect(loaded.every((c) => c.isHistorical)).toBe(true)
  })

  it('prunes to the most recent 50 exchanges', () => {
    const many = Array.from({ length: 60 }, (_, i) => card(String(i)))
    saveHistory(many)
    expect(loadHistory()).toHaveLength(50)
    expect(loadHistory()[0].id).toBe('10') // oldest 10 dropped
  })

  it('clearHistory empties storage', () => {
    saveHistory([card('1')])
    clearHistory()
    expect(loadHistory()).toEqual([])
  })

  it('getSessionDividerLabel includes today\'s date', () => {
    const label = getSessionDividerLabel()
    expect(label).toMatch(/New session/)
  })

  it('returns an empty array and clears storage when the stored value is not valid JSON', () => {
    localStorage.setItem('egazette_history', '{not json')
    localStorage.setItem('egazette_history_savedAt', String(Date.now()))
    expect(loadHistory()).toEqual([])
    expect(localStorage.getItem('egazette_history')).toBeNull()
  })

  it('returns an empty array and clears storage when the stored value is valid JSON but not an array', () => {
    localStorage.setItem('egazette_history', JSON.stringify({ not: 'an array' }))
    localStorage.setItem('egazette_history_savedAt', String(Date.now()))
    expect(loadHistory()).toEqual([])
    expect(localStorage.getItem('egazette_history')).toBeNull()
  })
})
