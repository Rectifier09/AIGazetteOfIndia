'use client'

import { useEffect, useRef, useState } from 'react'

interface InputBarProps {
  onSubmit: (question: string) => void
  prefill: string
}

export default function InputBar({ onSubmit, prefill }: InputBarProps) {
  const [value, setValue] = useState(prefill)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => setValue(prefill), [prefill])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  function submit() {
    if (!value.trim()) return
    onSubmit(value)
    setValue('')
  }

  return (
    <div className="sticky bottom-0 p-3 flex gap-2 bg-[rgba(251,251,250,0.75)] backdrop-blur-md border-t border-white/50">
      <textarea
        ref={textareaRef}
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
        className="flex-1 bg-white/60 border border-neutral-300 rounded-sm px-3 py-2 resize-none overflow-hidden focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent"
      />
      <button
        onClick={submit}
        className="bg-accent text-white rounded-sm px-4 py-2 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2"
      >
        Ask
      </button>
    </div>
  )
}
