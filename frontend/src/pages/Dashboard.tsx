import { useEffect, useState } from 'react'
import { api, type Alert, type Stats } from '../api'
import EntityGraph from '../components/EntityGraph'
import { Button, Card, ErrorNote, Risk, Stat, inputClass, label, when } from '../ui'

const EMPTY = { customer: '', transaction: '', product: '', risk_level: '', date_from: '', date_to: '', detection_type: '' }
const TYPES = [
  'account_takeover', 'suspicious_transfer', 'shared_device', 'repeated_login_failures', 'suspicious_loan_application',
  'new_device', 'amount_spike', 'new_beneficiary', 'mule_beneficiary', 'velocity', 'foreign_ip', 'off_hours',
]
const PAGE_SIZE = 10

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [filters, setFilters] = useState(EMPTY)
  const [selected, setSelected] = useState<Alert | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [rerun, setRerun] = useState<string | null>(null)
  const [runs, setRuns] = useState(0)
  const [page, setPage] = useState(1)

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setError(e.message))
  }, [runs])

  useEffect(() => {
    let current = true // a slower, older response must not overwrite these filters
    api.alerts(filters)
      .then((rows) => {
        if (!current) return
        setAlerts(rows)
        setPage(1)
      })
      .catch((e) => {
        if (current) setError(e.message)
      })
    return () => {
      current = false
    }
  }, [filters, runs])

  useEffect(() => {
    if (selected) document.getElementById('alert-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [selected])

  const focus = selected ?? alerts[0] ?? null

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setFilters((f) => ({ ...f, [key]: e.target.value }))

  const totalPages = Math.max(1, Math.ceil(alerts.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageRows = alerts.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <div className="flex items-center gap-3">
          {rerun && <span className="text-sm text-slate-600">{rerun}</span>}
          <Button onClick={() => api.rerun().then((r) => { setRerun(`Detection re-run: ${r.alerts_created} new Alerts`); setRuns((n) => n + 1) })}>Re-run detection</Button>
        </div>
      </div>
      <ErrorNote message={error} />
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Records processed" value={stats.records_processed.toLocaleString('en-IN')} tooltip="Total records processed by detection." />
          <Stat label="Flagged events" value={stats.flagged_events} tooltip="Events flagged as suspicious." />
          <Card title="Risk distribution" tooltip="Counts of Alerts by risk level." className="sm:col-span-1">
            <div className="space-y-2 text-sm">
              {(['high', 'medium', 'low'] as const).map((level) => (
                <div key={level} className="flex items-center justify-between">
                  <Risk level={level} />
                  <span className="tabular-nums font-medium">{stats.risk_distribution[level] ?? 0}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card title="Fraud categories" tooltip="Alerts grouped by detection category.">
            <div className="space-y-2 text-sm">
              {Object.entries(stats.fraud_categories).map(([name, count]) => (
                <div key={name} className="flex items-center justify-between gap-2">
                  <span className="text-slate-600">{label(name)}</span>
                  <span className="tabular-nums font-medium">{count}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
      <Card title={`Alerts (${alerts.length})`} tooltip="Alerts created by detection; click a row for details." action={
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <span>Page {currentPage} of {totalPages}</span>
          <Button disabled={currentPage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Prev</Button>
          <Button disabled={currentPage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Next</Button>
        </div>
      }>
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
              {pageRows.map((a) => (
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
        </div>
      </Card>
      <div id="alert-detail" className="scroll-mt-4 space-y-4">
      {selected && (
        <Card
          title={`${selected.id}: why it was flagged`}
          tooltip="Rule hits and supporting records for this Alert."
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
      {focus && <EntityGraph key={`${focus.id}-${runs}`} alert={focus} />}
      </div>
    </>
  )
}
