import { useEffect, useRef, useState } from 'react'

interface StreamEvent {
  type: string
  content?: string
  agent?: string
  timestamp?: string
}

interface Props {
  taskId: string
}

export default function AgentStream({ taskId }: Props) {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [connected, setConnected] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!taskId) return
    const es = new EventSource(`/tasks/${taskId}/stream`)
    esRef.current = es

    es.onopen = () => setConnected(true)
    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        setEvents((prev) => [...prev.slice(-500), event])
      } catch {}
    }
    es.addEventListener('done', () => {
      setConnected(false)
      es.close()
    })
    es.onerror = () => setConnected(false)

    return () => { es.close(); esRef.current = null }
  }, [taskId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 flex flex-col" style={{ height: 380 }}>
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
        <h3 className="text-sm font-semibold text-gray-400">Agent Stream</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full ${connected ? 'bg-green-900 text-green-300' : 'bg-gray-800 text-gray-500'}`}>
          {connected ? 'live' : 'disconnected'}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-xs">
        {events.length === 0 && (
          <p className="text-gray-600">Waiting for agent output...</p>
        )}
        {events.map((ev, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-gray-600 shrink-0">{ev.agent ?? 'system'}</span>
            <span className={`${ev.type === 'error' ? 'text-red-400' : ev.type === 'tool' ? 'text-yellow-400' : 'text-gray-300'}`}>
              {ev.content ?? JSON.stringify(ev)}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
