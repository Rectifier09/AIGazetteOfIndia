import { askQuestion } from '@/lib/api'

describe('askQuestion', () => {
  beforeEach(() => {
    global.fetch = jest.fn()
  })

  it('posts the question and history, returns the parsed response', async () => {
    const mockResponse = {
      answer: 'Yes, in force.',
      refused: false,
      citations: [{ source: 'gujarat', gazette_id: 'Gujarat-Extra-62', part: 'Part IV-A', section: null, notification_date: '20th May, 2026', passage: '...', source_url: null }],
      disclaimer: 'This is not legal advice — verify against the original Gazette.',
    }
    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    })

    const result = await askQuestion('Is it in force in Gujarat?', [])

    expect(result).toEqual(mockResponse)
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/ask'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ question: 'Is it in force in Gujarat?', history: [] }),
      })
    )
  })

  it('throws when the response is not ok', async () => {
    ;(global.fetch as jest.Mock).mockResolvedValue({ ok: false, status: 500 })
    await expect(askQuestion('anything', [])).rejects.toThrow()
  })
})
