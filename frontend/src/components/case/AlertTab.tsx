import type { Alert, Case } from '../../api'
import { label, when } from '../../ui'

export default function AlertTab({ alert, records }: { alert: Alert; records: Case['supporting_records'] }) {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold">{alert.id}</h2>
        <span className="text-sm text-slate-500">{when(alert.created_at)}</span>
      </div>
      <div className="rounded-md border border-slate-200 p-3">
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="text-xs font-semibold text-slate-500">Why it was flagged</h3>
          <span className="flex items-baseline gap-3">
            <a className="text-xs text-blue-700 underline" href="#/rules">How rules work</a>
            <span className="text-sm font-semibold">Score {alert.score}</span>
          </span>
        </div>
        <ul className="space-y-1 text-sm">
          {alert.rule_hits.map((h) => (
            <li key={h.rule} className="flex justify-between gap-4"><span>{h.reason}</span><span className="tabular-nums text-slate-500">+{h.points}</span></li>
          ))}
        </ul>
      </div>
      {records.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-slate-500">Supporting records</h3>
          {records.map((r) => (
            <details key={r.source_ref} className="border-t border-slate-100 py-1.5 text-sm">
              <summary className="cursor-pointer">{label(r.kind)} {r.source_ref}</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(r.data, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}
