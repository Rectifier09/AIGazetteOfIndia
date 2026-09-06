'use client'

import { useEffect, useState } from 'react'

interface InputBarProps {
  onSubmit: (question: string) => void
  prefill: string
}

export default function InputBar({ onSubmit, prefill }: InputBarProps) {
  const [value, setValue] = useState(prefill)

  useEffect(() => setValue(prefill), [prefill])

  function submit() {
    if (!value.trim()) return
    onSubmit(value)
    setValue('')
  }

  return (
    <div className="sticky bottom-0 p-3 flex gap-2 bg-[rgba(251,251,250,0.75)] backdrop-blur-md border-t border-white/50">
      <textarea
        role="textbox"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Ask a question..."
        rows={1}
        className="flex-1 bg-white/60 border border-neutral-300 rounded-sm px-3 py-2 resize-none"
      />
      <button onClick={submit} className="bg-accent text-white rounded-sm px-4 py-2">Ask</button>
    </div>
  )
}
