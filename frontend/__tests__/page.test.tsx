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
})
