import { useEffect, useState } from 'react'
import { api, type Alert, type Stats } from '../api'
import { Button, Card, ErrorNote, Risk, Stat, inputClass, label, when } from '../ui'

const EMPTY = { customer: '', transaction: '', product: '', risk_level: '', date_from: '', date_to: '', detection_type: '' }
const TYPES = [
  'account_takeover', 'suspicious_transfer', 'shared_device', 'repeated_login_failures', 'suspicious_loan_application',
  'new_device', 'amount_spike', 'new_beneficiary', 'mule_beneficiary', 'velocity', 'foreign_ip', 'off_hours',
]

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [filters, setFilters] = useState(EMPTY)
  const [selected, setSelected] = useState<Alert | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rerun, setRerun] = useState<string | null>(null)

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setError(e.message))
  }, [rerun])

  useEffect(() => {
    api.alerts(filters).then(setAlerts).catch((e) => setError(e.message))
  }, [filters, rerun])

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }))

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <div className="flex items-center gap-3">
          {rerun && <span className="text-sm text-slate-600">{rerun}</span>}
          <Button onClick={() => api.rerun().then((r) => setRerun(`Detection re-run: ${r.alerts_created} new Alerts`))}>Re-run detection</Button>
        </div>
      </div>
      <ErrorNote message={error} />
      {stats && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Records processed" value={stats.records_processed.toLocaleString('en-IN')} />
          <Stat label="Flagged events" value={stats.flagged_events} />
          <Card title="Risk distribution">
            <div className="space-y-1 text-sm">
              {(['high', 'medium', 'low'] as const).map((level) => (
                <div key={level} className="flex justify-between"><Risk level={level} /><span className="tabular-nums">{stats.risk_distribution[level] ?? 0}</span></div>
              ))}
            </div>
          </Card>
          <Card title="Fraud categories">
            <div className="space-y-1 text-sm">
              {Object.entries(stats.fraud_categories).map(([name, count]) => (
                <div key={name} className="flex justify-between gap-2"><span>{label(name)}</span><span className="tabular-nums">{count}</span></div>
              ))}
            </div>
          </Card>
        </div>
      )}
      <Card title={`Alerts (${alerts.length})`}>
        <div className="mb-3 flex flex-wrap gap-2">
          <input aria-label="Customer" placeholder="Customer" className={inputClass} value={filters.customer} onChange={set('customer')} />
          <input aria-label="Transaction" placeholder="Transaction" className={inputClass} value={filters.transaction} onChange={set('transaction')} />
          <select aria-label="Product" className={inputClass} value={filters.product} onChange={set('product')}>
            <option value="">All products</option><option value="core_banking">Core banking</option><option value="lending">Lending</option>
          </select>
          <select aria-label="Risk level" className={inputClass} value={filters.risk_level} onChange={set('risk_level')}>
            <option value="">All risk levels</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
          </select>
          <input aria-label="From date" type="date" className={inputClass} value={filters.date_from} onChange={set('date_from')} />
          <input aria-label="To date" type="date" className={inputClass} value={filters.date_to} onChange={set('date_to')} />
          <select aria-label="Detection type" className={inputClass} value={filters.detection_type} onChange={set('detection_type')}>
            <option value="">All detection types</option>
            {TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </select>
          <Button onClick={() => setFilters(EMPTY)}>Clear</Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500">
              <tr><th className="py-1 pr-3">Alert</th><th className="pr-3">Risk</th><th className="pr-3">Score</th><th className="pr-3">Category</th><th className="pr-3">Customer</th><th className="pr-3">Subject</th><th>Time</th></tr>
            </thead>
            <tbody>
              {alerts.slice(0, 100).map((a) => (
                <tr key={a.id} onClick={() => setSelected(a)} className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${selected?.id === a.id ? 'bg-blue-50' : ''}`}>
                  <td className="py-1.5 pr-3">{a.id}</td>
                  <td className="pr-3"><Risk level={a.risk_level} /></td>
                  <td className="pr-3 tabular-nums">{a.score}</td>
                  <td className="pr-3">{label(a.category)}</td>
                  <td className="pr-3">{a.customer_id}</td>
                  <td className="pr-3">{a.transaction_id ?? a.application_id ?? a.device_id ?? a.account_id}</td>
                  <td>{when(a.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {alerts.length === 0 && <p className="py-4 text-sm text-slate-600">No Alerts match. Load sample data on the Upload page if this is a fresh start.</p>}
          {alerts.length > 100 && <p className="pt-2 text-sm text-slate-600">Showing the first 100. Use the filters to narrow this down.</p>}
        </div>
      </Card>
      {selected && (
        <Card
          title={`${selected.id}: why it was flagged`}
          action={selected.case_id ? <a className="text-sm text-blue-700 underline" href={`#/cases/${selected.case_id}`}>Open {selected.case_id}</a> : <span className="text-sm text-slate-500">Below the actionable threshold, so no Case</span>}
        >
          <ul className="space-y-1 text-sm">
            {selected.rule_hits.map((h) => (
              <li key={h.rule} className="flex justify-between gap-4"><span>{h.reason}</span><span className="tabular-nums text-slate-500">+{h.points}</span></li>
            ))}
          </ul>
          <h3 className="mt-3 text-xs font-semibold text-slate-500">Supporting records</h3>
          {selected.supporting_records.map((r) => (
            <details key={r.source_ref} className="mt-1 text-sm">
              <summary className="cursor-pointer">{label(r.kind)} {r.source_ref}</summary>
              <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(r.data, null, 2)}</pre>
            </details>
          ))}
        </Card>
      )}
    </>
  )
}
