'use client'

import { useEffect, useState } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ScopeBanner from '@/components/ScopeBanner'
import QACard from '@/components/QACard'
import InputBar from '@/components/InputBar'
import { askQuestion } from '@/lib/api'
import { loadHistory, saveHistory, clearHistory, getSessionDividerLabel } from '@/lib/history'
import type { QACardData } from '@/lib/types'

const EXAMPLE_QUESTIONS = [
  'Is the Code on Wages in force in Gujarat?',
  'Which notification amended a prior rule?',
  'When does a rule take effect?',
]

export default function Page() {
  const [historicalCards, setHistoricalCards] = useState<QACardData[]>([])
  const [sessionCards, setSessionCards] = useState<QACardData[]>([])
  const [prefill, setPrefill] = useState('')
  // Bumped on every example-chip click (even re-clicks of the same chip) and
  // used as InputBar's `key` so it fully remounts and re-initializes its
  // internal text state from `prefill`. Without this, clicking the same
  // example twice in a row (with an edit in between) leaves the field
  // showing the edit, because InputBar's `useEffect(() => setValue(prefill),
  // [prefill])` only fires when the `prefill` string itself changes.
  const [prefillNonce, setPrefillNonce] = useState(0)

  useEffect(() => {
    setHistoricalCards(loadHistory())
  }, [])

  useEffect(() => {
    if (sessionCards.length > 0) {
      saveHistory([...historicalCards, ...sessionCards])
    }
  }, [sessionCards])

  async function handleSubmit(question: string) {
    const id = uuidv4()
    setSessionCards((prev) => [...prev, { id, question, status: 'loading-searching', isHistorical: false }])

    const historyContext = sessionCards
      .filter((c) => c.status === 'answered')
      .map((c) => ({ question: c.question, answer: c.answer! }))

    try {
      const responsePromise = askQuestion(question, historyContext)
      // Yield a tick before flipping to 'loading-drafting': without this,
      // both status updates happen synchronously in the same batch (before
      // React ever commits/paints 'loading-searching'), so the searching
      // indicator would never actually be visible — to users or to tests.
      await Promise.resolve()
      setSessionCards((prev) => prev.map((c) => (c.id === id ? { ...c, status: 'loading-drafting' } : c)))
      const response = await responsePromise
      setSessionCards((prev) =>
        prev.map((c) =>
          c.id === id
            ? { ...c, status: response.refused ? 'refused' : 'answered', answer: response.answer, citations: response.citations, disclaimer: response.disclaimer }
            : c
        )
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : undefined
      setSessionCards((prev) => prev.map((c) => (c.id === id ? { ...c, status: 'error', answer: message } : c)))
    }
  }

  function handleRetry(id: string) {
    const card = sessionCards.find((c) => c.id === id)
    if (card) handleSubmit(card.question)
  }

  function handleClearHistory() {
    clearHistory()
    setHistoricalCards([])
  }

  function handleExampleClick(question: string) {
    setPrefill(question)
    setPrefillNonce((n) => n + 1)
  }

  const allCards = [...historicalCards, ...sessionCards]

  return (
    <main className="max-w-2xl mx-auto flex flex-col h-screen bg-[#FBFBFA]">
      <header className="sticky top-0 z-10 px-4 py-3 bg-[rgba(251,251,250,0.72)] backdrop-blur-md border-b border-white/50">
        <h1 className="font-serif text-lg text-accent">
          AI Gazette of India <span className="font-sans text-sm font-normal opacity-50">· Labour Codes</span>
        </h1>
      </header>
      <ScopeBanner
        collapsed={allCards.length > 0}
        onClearHistory={handleClearHistory}
        exampleQuestions={EXAMPLE_QUESTIONS}
        onExampleClick={handleExampleClick}
      />
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {historicalCards.length > 0 && (
          <>
            {historicalCards.map((c) => <QACard key={c.id} data={c} onRetry={handleRetry} />)}
            <p className="text-center text-xs text-neutral-400 my-3">── {getSessionDividerLabel()} ──</p>
          </>
        )}
        {sessionCards.map((c) => <QACard key={c.id} data={c} onRetry={handleRetry} />)}
      </div>
      <InputBar key={prefillNonce} onSubmit={handleSubmit} prefill={prefill} />
    </main>
  )
}
