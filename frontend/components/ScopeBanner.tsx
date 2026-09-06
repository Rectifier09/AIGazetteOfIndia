'use client'

import { useState } from 'react'
import { Info } from 'lucide-react'

interface ScopeBannerProps {
  collapsed: boolean
  onClearHistory: () => void
  exampleQuestions: string[]
  onExampleClick: (question: string) => void
}

export default function ScopeBanner({ collapsed, onClearHistory, exampleQuestions, onExampleClick }: ScopeBannerProps) {
  const [expanded, setExpanded] = useState(false)

  if (collapsed && !expanded) {
    return (
      <div className="flex justify-between items-center gap-3 px-4 py-2 mx-3 my-2 text-sm text-[#33475b] bg-[rgba(238,242,246,0.72)] backdrop-blur-md rounded-full">
        <button onClick={() => setExpanded(true)} className="flex items-center gap-2 text-left">
          <Info size={16} className="text-accent shrink-0" />
          Covers: Code on Wages · Industrial Relations Code · OSH Code · Code on Social Security — Central &amp; Gujarat Gazette only
        </button>
        <button onClick={onClearHistory} className="underline text-neutral-500 hover:text-neutral-800 shrink-0">Clear history</button>
      </div>
    )
  }

  return (
    <div className="px-4 py-4 mx-3 my-3 bg-[rgba(238,242,246,0.72)] backdrop-blur-md rounded-lg">
      <p className="text-sm text-[#33475b] flex gap-2">
        <Info size={16} className="text-accent shrink-0 mt-0.5" />
        <span>
          Covers: Code on Wages · Industrial Relations Code · OSH Code · Code on Social Security
          <br />
          Sources: Central Gazette + Gujarat Gazette
        </span>
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {exampleQuestions.map((q) => (
          <button
            key={q}
            onClick={() => onExampleClick(q)}
            className="text-sm border border-neutral-300 rounded-full px-3 py-1 hover:bg-white/50"
          >
            {q}
          </button>
        ))}
      </div>
      <button onClick={onClearHistory} className="mt-3 text-sm underline text-neutral-500 hover:text-neutral-800">
        Clear history
      </button>
    </div>
  )
}
