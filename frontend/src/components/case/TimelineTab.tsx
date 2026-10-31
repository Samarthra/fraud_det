import type { CaseDetail } from '../../api'
import { Badge, label, when } from '../../ui'

const TONE = { core_banking: 'slate', lending: 'blue', insurance: 'amber' } as const

export default function TimelineTab({ events }: { events: NonNullable<CaseDetail['timeline']> }) {
  if (events.length === 0) return <p className="text-sm text-slate-600">No events found.</p>
  return (
    <ol className="mx-auto max-w-3xl space-y-3 border-l-2 border-slate-200 pl-4 text-sm">
      {events.map((e, i) => (
        <li key={`${e.at}-${e.source_ref}-${i}`} className="relative">
          <span className={`absolute -left-[1.4rem] top-1.5 h-2.5 w-2.5 rounded-full ${e.kind === 'alert' ? 'bg-red-600' : 'bg-slate-400'}`} />
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>{when(e.at)}</span>
            <Badge tone={TONE[e.system]}>{label(e.system)}</Badge>
            <span>{e.source_ref}</span>
          </div>
          <p className={e.kind === 'alert' ? 'font-medium' : ''}>{e.summary}</p>
        </li>
      ))}
    </ol>
  )
}
