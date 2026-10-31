import { useEffect, useState } from 'react'
import { api, type Case } from '../api'
import { Badge, Card, ErrorNote, PriorityBadge, Risk, label, money } from '../ui'

export function currentDecision(c: Case) {
  return c.decisions.length ? c.decisions[c.decisions.length - 1].decision : null
}

export default function Cases() {
  const [cases, setCases] = useState<Case[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.cases()
      .then(setCases)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <>
      <div>
        <h1 className="text-xl font-semibold">Case queue</h1>
        <p className="text-sm text-slate-600">Ranked by severity, financial exposure, related Alerts and confidence. Linked Alerts appear as one Case.</p>
      </div>
      <ErrorNote message={error} />
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr><th className="py-1 pr-3">Case</th><th className="pr-3">Priority</th><th className="pr-3">Risk</th><th className="pr-3">Category</th><th className="pr-3">Exposure</th><th className="pr-3">Alerts</th><th className="pr-3">Systems</th><th className="pr-3">Account</th><th className="pr-3">Status</th><th>Decision</th></tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="py-1.5 pr-3"><a className="text-blue-700 underline" href={`#/cases/${c.id}`}>{c.id}</a></td>
                  <td className="pr-3">{c.priority && <span className="flex items-center gap-1.5"><PriorityBadge band={c.priority.band} /><span className="tabular-nums text-slate-500">{c.priority.score}</span></span>}</td>
                  <td className="pr-3"><Risk level={c.risk_level} /></td>
                  <td className="pr-3">{label(c.category)}</td>
                  <td className="pr-3 tabular-nums">{c.priority ? money(c.priority.exposure) : '—'}</td>
                  <td className="pr-3 tabular-nums">{c.alert_ids?.length ?? 1}</td>
                  <td className="pr-3">{c.products?.map(label).join(', ')}</td>
                  <td className="pr-3">{c.account_id}</td>
                  <td className="pr-3"><Badge>{label(c.status)}</Badge></td>
                  <td>{currentDecision(c) ? label(currentDecision(c)!) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {cases.length === 0 && !error && <p className="py-4 text-sm text-slate-600">No Cases yet.</p>}
        </div>
      </Card>
    </>
  )
}
