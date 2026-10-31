import { useEffect, useMemo, useRef, useState } from 'react'
import type { Evidence } from '../../api'
import { Button, label, when } from '../../ui'

const ISO = /^\d{4}-\d{2}-\d{2}T/
const MONEY = new Set(['amount', 'median_outgoing_30d'])

function display(key: string, value: unknown) {
  if (Array.isArray(value)) return value.join(', ') || 'None'
  if (typeof value === 'number' && MONEY.has(key)) return `₹${value.toLocaleString('en-IN')}`
  if (typeof value === 'string' && ISO.test(value)) return when(value)
  return String(value)
}

function fields(data: Record<string, unknown>) {
  return Object.entries(data).filter(
    ([, value]) => value !== null && value !== '' && (typeof value !== 'object' || Array.isArray(value)),
  )
}

function EvidenceCard({ evidence, focused }: { evidence: Evidence; focused: boolean }) {
  const ref = useRef<HTMLLIElement>(null)
  const [raw, setRaw] = useState(false)

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [focused])

  return (
    <li ref={ref} id={evidence.id} className={`rounded-md border p-3 text-sm ${focused ? 'border-blue-500 ring-1 ring-blue-500' : 'border-slate-200'}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate"><span className="font-semibold">{evidence.id}</span> <span className="text-slate-500">{evidence.source_ref}</span></p>
        <button type="button" className="shrink-0 text-xs text-blue-700 underline" onClick={() => setRaw((v) => !v)}>{raw ? 'Hide raw' : 'View raw'}</button>
      </div>
      {raw ? (
        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(evidence.data, null, 2)}</pre>
      ) : (
        <dl className="mt-2 grid gap-x-6 gap-y-0.5 sm:grid-cols-2">
          {fields(evidence.data).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3">
              <dt className="text-slate-500">{label(key)}</dt>
              <dd className="min-w-0 truncate text-right" title={String(value)}>{display(key, value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  )
}

export default function EvidenceTab({
  evidence,
  open,
  onBack,
}: {
  evidence: Evidence[]
  open: string | null
  onBack?: () => void
}) {
  const [kind, setKind] = useState<string | null>(null)
  const counts = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of evidence) map.set(e.kind, (map.get(e.kind) ?? 0) + 1)
    return [...map.entries()]
  }, [evidence])
  const target = evidence.find((e) => e.id === open)
  const active = target && kind && target.kind !== kind ? null : kind
  const shown = active ? evidence.filter((e) => e.kind === active) : evidence

  if (evidence.length === 0) {
    return <p className="py-10 text-center text-sm text-slate-500">Evidence appears here as the agent gathers it.</p>
  }

  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        {onBack && <Button onClick={onBack}>Back to report</Button>}
        <FilterChip selected={!active} onClick={() => setKind(null)}>All ({evidence.length})</FilterChip>
        {counts.map(([name, count]) => (
          <FilterChip key={name} selected={active === name} onClick={() => setKind(name)}>{label(name)} ({count})</FilterChip>
        ))}
      </div>
      <ul className="space-y-2">
        {shown.map((e) => <EvidenceCard key={e.id} evidence={e} focused={e.id === open} />)}
      </ul>
    </div>
  )
}

function FilterChip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={`rounded-full px-2.5 py-1 text-xs ${selected ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
    >
      {children}
    </button>
  )
}
