import type { Alert } from '../../api'
import { Badge, Risk, label, when } from '../../ui'

function OneAlert({ alert, lead }: { alert: Alert; lead: boolean }) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{alert.id}</h3>
        {lead && <Badge tone="blue">Lead Alert</Badge>}
        <Risk level={alert.risk_level} />
        <Badge>{label(alert.product)}</Badge>
        <span className="text-sm text-slate-600">{label(alert.category)}</span>
        <span className="ml-auto text-sm text-slate-500">{when(alert.created_at)}</span>
      </div>
      <div className="mb-1 flex items-baseline justify-between">
        <h4 className="text-xs font-semibold text-slate-500">Why it was flagged</h4>
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
      {alert.supporting_records.length > 0 && (
        <div className="mt-2">
          <h4 className="mb-1 text-xs font-semibold text-slate-500">Supporting records</h4>
          {alert.supporting_records.map((r) => (
            <details key={r.kind + r.source_ref} className="border-t border-slate-100 py-1.5 text-sm">
              <summary className="cursor-pointer">{label(r.kind)} {r.source_ref}</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(r.data, null, 2)}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AlertTab({ alerts, leadId }: { alerts: Alert[]; leadId: string }) {
  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <p className="text-sm text-slate-600">Original Alerts, exactly as detection raised them. They never change.</p>
      {alerts.map((a) => <OneAlert key={a.id} alert={a} lead={a.id === leadId} />)}
    </div>
  )
}
