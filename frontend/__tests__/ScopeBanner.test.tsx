import { render, screen, fireEvent } from '@testing-library/react'
import ScopeBanner from '@/components/ScopeBanner'

const examples = ['How are wage disputes resolved?', 'What does section 56 say?']

describe('ScopeBanner', () => {
  it('shows full scope text and example chips when not collapsed', () => {
    render(<ScopeBanner collapsed={false} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    expect(screen.getByText(/Code on Wages/i)).toBeInTheDocument()
    expect(screen.getByText(examples[0])).toBeInTheDocument()
  })

  it('shows a compact one-line strip when collapsed', () => {
    render(<ScopeBanner collapsed={true} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    expect(screen.queryByText(examples[0])).not.toBeInTheDocument()
  })

  it('clicking an example chip calls onExampleClick with that question', () => {
    const onExampleClick = jest.fn()
    render(<ScopeBanner collapsed={false} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={onExampleClick} />)
    fireEvent.click(screen.getByText(examples[0]))
    expect(onExampleClick).toHaveBeenCalledWith(examples[0])
  })

  it('clicking Clear history calls onClearHistory', () => {
    const onClearHistory = jest.fn()
    render(<ScopeBanner collapsed={false} onClearHistory={onClearHistory} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    fireEvent.click(screen.getByText(/clear history/i))
    expect(onClearHistory).toHaveBeenCalled()
  })

  it('tapping the collapsed strip expands it to show example chips', () => {
    render(<ScopeBanner collapsed={true} onClearHistory={jest.fn()} exampleQuestions={examples} onExampleClick={jest.fn()} />)
    fireEvent.click(screen.getByText(/Covers:/i))
    expect(screen.getByText(examples[0])).toBeInTheDocument()
  })
})
