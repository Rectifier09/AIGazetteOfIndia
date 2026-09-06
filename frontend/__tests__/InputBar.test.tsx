import { render, screen, fireEvent } from '@testing-library/react'
import InputBar from '@/components/InputBar'

describe('InputBar', () => {
  it('submits the typed question on Enter and clears the input', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="" />)
    const textbox = screen.getByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'Is it in force?' } })
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: false })
    expect(onSubmit).toHaveBeenCalledWith('Is it in force?')
    expect((textbox as HTMLTextAreaElement).value).toBe('')
  })

  it('does not submit on Shift+Enter', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="" />)
    const textbox = screen.getByRole('textbox')
    fireEvent.change(textbox, { target: { value: 'line one' } })
    fireEvent.keyDown(textbox, { key: 'Enter', shiftKey: true })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('populates from prefill without auto-submitting', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="Example question?" />)
    expect(screen.getByRole('textbox')).toHaveValue('Example question?')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('clicking Ask submits the current value', () => {
    const onSubmit = jest.fn()
    render(<InputBar onSubmit={onSubmit} prefill="" />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'typed question' } })
    fireEvent.click(screen.getByText('Ask'))
    expect(onSubmit).toHaveBeenCalledWith('typed question')
  })
})
