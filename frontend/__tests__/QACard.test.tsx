import { render, screen, fireEvent } from '@testing-library/react'
import QACard from '@/components/QACard'
import type { QACardData } from '@/lib/types'

const base: QACardData = { id: '1', question: 'Is it in force in Gujarat?', status: 'answered', isHistorical: false }

describe('QACard', () => {
  it('shows the searching indicator while loading-searching', () => {
    render(<QACard data={{ ...base, status: 'loading-searching' }} onRetry={jest.fn()} />)
    expect(screen.getByText(/searching/i)).toBeInTheDocument()
  })

  it('shows the drafting indicator while loading-drafting', () => {
    render(<QACard data={{ ...base, status: 'loading-drafting' }} onRetry={jest.fn()} />)
    expect(screen.getByText(/drafting/i)).toBeInTheDocument()
  })

  it('shows the answer, an always-visible citation, and the disclaimer when answered', () => {
    render(
      <QACard
        data={{
          ...base,
          status: 'answered',
          answer: 'Yes, it is in force.',
          citations: [{ source: 'gujarat', gazette_id: 'Gujarat-Extra-62', part: 'Part IV-A', section: null, notification_date: '20th May, 2026', passage: 'quoted text', source_url: 'https://example.gov.in/doc.pdf' }],
          disclaimer: 'This is not legal advice — verify against the original Gazette.',
        }}
        onRetry={jest.fn()}
      />
    )
    expect(screen.getByText('Yes, it is in force.')).toBeInTheDocument()
    expect(screen.getByText(/Gujarat-Extra-62/)).toBeInTheDocument()
    expect(screen.getByText(/not legal advice/i)).toBeInTheDocument()
    expect(screen.getByText(/View original PDF/i)).toHaveAttribute('href', 'https://example.gov.in/doc.pdf')
    expect(screen.getByText(/View original PDF/i)).toHaveAttribute('target', '_blank')
  })

  it('shows the refusal message when refused', () => {
    render(<QACard data={{ ...base, status: 'refused', answer: "I couldn't find a notification matching this." }} onRetry={jest.fn()} />)
    expect(screen.getByText(/couldn't find/i)).toBeInTheDocument()
  })

  it('shows a retry button on error and calls onRetry with the card id', () => {
    const onRetry = jest.fn()
    render(<QACard data={{ ...base, status: 'error' }} onRetry={onRetry} />)
    fireEvent.click(screen.getByText(/try again/i))
    expect(onRetry).toHaveBeenCalledWith('1')
  })
})
