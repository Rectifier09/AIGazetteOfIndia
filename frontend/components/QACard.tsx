'use client'

import { Search, PenLine, TriangleAlert, ExternalLink } from 'lucide-react'
import type { QACardData } from '@/lib/types'

interface QACardProps {
  data: QACardData
  onRetry: (id: string) => void
}

export default function QACard({ data, onRetry }: QACardProps) {
  const borderClass =
    data.status === 'error' ? 'border-[#A13B3B]/40' : data.status === 'refused' ? 'border-[#B8860B]/40' : 'border-white/60'

  return (
    <div
      className={`border ${borderClass} rounded-xl p-6 mb-3 bg-[rgba(251,251,250,0.72)] backdrop-blur-md ${data.isHistorical ? 'opacity-60' : ''}`}
    >
      <p className="font-serif font-semibold text-lg mb-2 text-accent">Q: {data.question}</p>

      {data.status === 'loading-searching' && (
        <p className="text-neutral-500 flex items-center gap-2">
          <Search size={16} /> Searching Central &amp; Gujarat notifications…
        </p>
      )}
      {data.status === 'loading-drafting' && (
        <p className="text-neutral-500 flex items-center gap-2">
          <PenLine size={16} /> Drafting answer from matching notification(s)
        </p>
      )}

      {data.status === 'refused' && <p>{data.answer}</p>}

      {data.status === 'error' && (
        <div>
          <p className="text-[#A13B3B] flex items-center gap-2">
            <TriangleAlert size={16} /> Something went wrong answering this.
          </p>
          <button onClick={() => onRetry(data.id)} className="mt-2 underline text-[#A13B3B]">Try again</button>
        </div>
      )}

      {data.status === 'answered' && (
        <div>
          <p className="text-[15px] mb-4">{data.answer}</p>
          {data.citations?.map((c, i) => (
            <div
              key={i}
              className="font-mono text-xs bg-[rgba(245,244,239,0.45)] backdrop-blur-sm border border-white/40 rounded-md p-3 mb-2"
            >
              <p>Source: {c.source === 'central' ? 'Central Gazette' : 'Gujarat Government Gazette'} · {c.gazette_id} · {c.part}{c.section ? ` · ${c.section}` : ''} · {c.notification_date}</p>
              <p className="italic mt-1">&quot;{c.passage}&quot;</p>
              {c.source_url && (
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 underline text-[#0071E3] font-sans not-italic mt-1"
                >
                  View original PDF <ExternalLink size={12} />
                </a>
              )}
            </div>
          ))}
          <p className="text-[#9a9a94] text-xs mt-2 flex items-center gap-2">
            <TriangleAlert size={14} className="text-[#B8860B]" /> {data.disclaimer}
          </p>
        </div>
      )}
    </div>
  )
}
