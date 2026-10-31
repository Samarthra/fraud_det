import { useState } from 'react'
import { type CaseDetail, type RiskLevel } from '../../api'
import { Badge, Button, ErrorNote, PriorityBadge, Risk, inputClass, label, money, when } from '../../ui'

const LEVELS: RiskLevel[] = ['low', 'medium', 'high']

function Fact({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{name}</dt>
      <dd className="font-semibold tabular-nums">{children}</dd>
    </div>
  )
}

function Reclassify({ current, onSave }: { current: RiskLevel; onSave: (level: RiskLevel, reason: string) => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState<RiskLevel>(current === 'high' ? 'medium' : 'high')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setError(null)
    try {
      await onSave(level, reason)
      setOpen(false)
      setReason('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (!open) return <Button onClick={() => setOpen(true)}>Change risk classification</Button>
  return (
    <div className="space-y-2 rounded-md border border-slate-200 p-3">
      <select aria-label="New risk level" className={`${inputClass} w-full`} value={level} onChange={(e) => setLevel(e.target.value as RiskLevel)}>
        {LEVELS.filter((l) => l !== current).map((l) => <option key={l} value={l}>{label(l)}</option>)}
      </select>
      <textarea aria-label="Reason" rows={2} className={`${inputClass} w-full`} placeholder="Why is the classification changing?" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="flex gap-2">
        <Button primary onClick={save}>Save</Button>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
      </div>
      <ErrorNote message={error} />
      <p className="text-xs text-slate-500">The original classification stays on the Alerts and in the history.</p>
    </div>
  )
}

function Separate({ alertId, onSeparate }: { alertId: string; onSeparate: (reason: string) => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  if (!open) return <button type="button" className="text-xs text-blue-700 underline" onClick={() => setOpen(true)}>Separate</button>
  return (
    <div className="mt-1 w-full space-y-1">
      <input aria-label={`Reason for separating ${alertId}`} className={`${inputClass} w-full`} placeholder="Why doesn't this Alert belong here?" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="flex gap-2">
        <Button onClick={() => onSeparate(reason).catch((e) => setError(e.message))}>Separate {alertId}</Button>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
      </div>
      <ErrorNote message={error} />
    </div>
  )
}

export default function OverviewTab({
  detail,
  onReclassify,
  onSeparate,
}: {
  detail: CaseDetail
  onReclassify: (level: RiskLevel, reason: string) => Promise<void>
  onSeparate: (alertId: string, reason: string) => Promise<void>
}) {
  const { case: item, alerts = [], reasons = [], classifications = [] } = detail
  const priority = item.priority!
  const indicators = alerts.flatMap((a) => a.rule_hits.map((h) => ({ ...h, alert: a.id })))
  const recommendations = item.decisions.filter((d) => d.decision.endsWith('_recommended'))

  return (
    <div className="mx-auto max-w-4xl space-y-5 text-sm">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-semibold">Risk assessment</h2>
          <PriorityBadge band={priority.band} />
          <span className="text-slate-600">Priority {priority.score} of 100</span>
        </div>
        {priority.needs_review && (
          <p className="rounded-md bg-violet-100 p-2 text-violet-900">Marked for further review: only one kind of signal supports this Case, so it isn't ranked as high risk yet.</p>
        )}
        <dl className="grid grid-cols-2 gap-3 rounded-md border border-slate-200 p-3 sm:grid-cols-5">
          <Fact name="Severity">{priority.severity}</Fact>
          <Fact name="Exposure">{money(priority.exposure)}</Fact>
          <Fact name="Related Alerts">{priority.related_events}</Fact>
          <Fact name="Confidence">{label(priority.confidence)}</Fact>
          <Fact name="Risk"><Risk level={item.risk_level} /></Fact>
        </dl>
        <ul className="list-disc space-y-0.5 pl-5 text-slate-700">{priority.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        {classifications.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-500">Classification history (original: {item.original_risk_level})</h3>
            <ul className="mt-1 space-y-1">
              {classifications.map((c) => (
                <li key={c.at + c.risk_level}>{label(c.previous)} to {c.risk_level} by {c.analyst}, {when(c.at)}: {c.reason}</li>
              ))}
            </ul>
          </div>
        )}
        <Reclassify key={item.risk_level} current={item.risk_level} onSave={onReclassify} />
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">Alerts in this Case ({alerts.length})</h2>
        {reasons.length > 0 && (
          <div className="rounded-md bg-blue-50 p-3 text-slate-800">
            <h3 className="mb-1 text-xs font-semibold text-slate-600">Why these were grouped</h3>
            <ul className="space-y-1">{reasons.map((r) => <li key={r.kind + r.value}>{r.explanation}</li>)}</ul>
          </div>
        )}
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
          {alerts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
              <strong>{a.id}</strong>
              {a.id === item.alert_id && <Badge tone="blue">Lead</Badge>}
              <Risk level={a.risk_level} />
              <Badge>{label(a.product)}</Badge>
              <span className="text-slate-600">{label(a.category)}, {a.account_id}</span>
              <span className="ml-auto text-xs text-slate-500">{when(a.created_at)}</span>
              {a.id !== item.alert_id && <Separate alertId={a.id} onSeparate={(reason) => onSeparate(a.id, reason)} />}
            </li>
          ))}
        </ul>
        {alerts.length > 1 && <p className="text-xs text-slate-500">An Investigation looks into the lead Alert. The others stay here with their original evidence.</p>}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">Fraud indicators ({indicators.length})</h2>
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
          {indicators.map((h) => (
            <li key={h.alert + h.rule} className="flex justify-between gap-3 px-3 py-1.5">
              <span>{h.reason}</span>
              <span className="whitespace-nowrap text-xs text-slate-500">{h.alert}, +{h.points}</span>
            </li>
          ))}
        </ul>
      </section>

      {recommendations.length > 0 && (
        <section className="space-y-2">
          <h2 className="font-semibold">Recommendations on record</h2>
          <ul className="space-y-1">
            {recommendations.map((r) => <li key={r.at + r.decision}>{label(r.decision)} by {r.analyst}: {r.note}</li>)}
          </ul>
          <p className="text-xs text-slate-500">Recommendations only. No action has been taken on any account or transaction.</p>
        </section>
      )}
    </div>
  )
}
