import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Page from '@/app/page'
import * as api from '@/lib/api'

// NOTE: jest.mock() takes a bare module-specifier string that Jest's own
// resolver must resolve directly — unlike static `import` specifiers, it is
// not rewritten by the SWC/tsconfig "@/*" path-alias transform used for the
// `import` above. This project's jest config (next/jest) does not register
// a moduleNameMapper for "@/*", so the aliased form here would fail with
// "Cannot find module '@/lib/api'". A relative path resolves to the same
// underlying file and mocks the same module instance.
jest.mock('../lib/api')

describe('Page', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  it('asking a question renders a loading state then the answered card, and only same-session history is sent as context', async () => {
    ;(api.askQuestion as jest.Mock).mockResolvedValue({
      answer: 'Yes.', refused: false,
      citations: [{ source: 'gujarat', gazette_id: 'Gujarat-Extra-62', part: 'Part IV-A', section: null, notification_date: '20th May, 2026', passage: 'x', source_url: null }],
      disclaimer: 'not legal advice',
    })

    render(<Page />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Is it in force?' } })
    fireEvent.click(screen.getByText('Ask'))

    expect(screen.getByText(/searching/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Yes.')).toBeInTheDocument())
    expect(api.askQuestion).toHaveBeenCalledWith('Is it in force?', [])
  })

  it('restored historical cards render above a session divider and are not sent as history context', async () => {
    localStorage.setItem(
      'egazette_history',
      JSON.stringify([{ id: 'old1', question: 'Old question?', status: 'answered', answer: 'Old answer', citations: [], disclaimer: 'd', isHistorical: false }])
    )
    ;(api.askQuestion as jest.Mock).mockResolvedValue({ answer: 'New answer', refused: false, citations: [], disclaimer: 'd' })

    render(<Page />)
    expect(screen.getByText(/New session/i)).toBeInTheDocument()
    expect(screen.getByText(/Old question\?/)).toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'New question?' } })
    fireEvent.click(screen.getByText('Ask'))
    await waitFor(() => expect(api.askQuestion).toHaveBeenCalled())

    expect(api.askQuestion).toHaveBeenCalledWith('New question?', [])
  })

  it('clicking Clear history removes stored cards', () => {
    localStorage.setItem('egazette_history', JSON.stringify([{ id: 'old1', question: 'Old?', status: 'answered', isHistorical: false }]))
    render(<Page />)
    fireEvent.click(screen.getByText(/clear history/i))
    expect(localStorage.getItem('egazette_history')).toBeNull()
  })

  it('shows the backend error detail on the error card when the request fails', async () => {
    ;(api.askQuestion as jest.Mock).mockRejectedValue(
      new Error('The database is temporarily unavailable — please try again shortly.')
    )

    render(<Page />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Is it in force?' } })
    fireEvent.click(screen.getByText('Ask'))

    await waitFor(() =>
      expect(
        screen.getByText('The database is temporarily unavailable — please try again shortly.')
      ).toBeInTheDocument()
    )
    // The generic fallback text should not be shown when a real detail message is available.
    expect(screen.queryByText('Something went wrong answering this.')).not.toBeInTheDocument()
  })

  it('clicking the same example chip again re-populates the input, even after it was edited', () => {
    render(<Page />)
    const exampleText = 'Is the Code on Wages in force in Gujarat?'

    fireEvent.click(screen.getByText(exampleText))
    expect(screen.getByRole('textbox')).toHaveValue(exampleText)

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'something the user typed instead' } })
    expect(screen.getByRole('textbox')).toHaveValue('something the user typed instead')

    // Re-clicking the SAME chip: the `prefill` string prop doesn't change,
    // so this only works if page.tsx forces InputBar to remount (via a
    // changing `key`) rather than relying on InputBar's prefill effect.
    fireEvent.click(screen.getByText(exampleText))
    expect(screen.getByRole('textbox')).toHaveValue(exampleText)
  })

  it('does not resurrect cleared cards when a new question is answered afterward', async () => {
    ;(api.askQuestion as jest.Mock).mockResolvedValue({ answer: 'A1', refused: false, citations: [], disclaimer: 'd' })

    render(<Page />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Q1' } })
    fireEvent.click(screen.getByText('Ask'))
    await waitFor(() => expect(screen.getByText('A1')).toBeInTheDocument())
    expect(localStorage.getItem('egazette_history')).not.toBeNull()

    fireEvent.click(screen.getByText(/clear history/i))
    expect(localStorage.getItem('egazette_history')).toBeNull()

    ;(api.askQuestion as jest.Mock).mockResolvedValue({ answer: 'A2', refused: false, citations: [], disclaimer: 'd' })
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Q2' } })
    fireEvent.click(screen.getByText('Ask'))
    await waitFor(() => expect(screen.getByText('A2')).toBeInTheDocument())

    const stored = JSON.parse(localStorage.getItem('egazette_history') || '[]')
    expect(stored).toHaveLength(1)
    expect(stored[0].question).toBe('Q2')
    expect(screen.queryByText(/Q: Q1/)).not.toBeInTheDocument()
  })

  it('does not persist a card that is still loading (e.g. after a refresh mid-request)', async () => {
    ;(api.askQuestion as jest.Mock).mockReturnValue(new Promise(() => {})) // never resolves

    render(<Page />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Is it in force?' } })
    fireEvent.click(screen.getByText('Ask'))

    await waitFor(() => expect(screen.getByText(/drafting/i)).toBeInTheDocument())
    expect(localStorage.getItem('egazette_history')).toBeNull()
  })
})
