import { useEffect, useState } from 'react'
import { api, type AuditRow } from '../api'
import { Card, ErrorNote, label, when } from '../ui'

export default function Governance() {
  const [rows, setRows] = useState<AuditRow[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.audit().then(setRows).catch((e) => setError(e.message))
  }, [])

  return (
    <>
      <h1 className="text-xl font-semibold">Governance</h1>
      <p className="rounded-md bg-slate-100 p-3 text-sm">These are demonstrations of controls, not compliance claims.</p>
      <ErrorNote message={error} />
      <Card title="Audit trail">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500"><tr><th className="py-1 pr-3">Time</th><th className="pr-3">Event</th><th className="pr-3">Details</th><th>Trace</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.seq} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap py-1.5 pr-3">{when(r.at)}</td>
                  <td className="whitespace-nowrap pr-3">{label(r.event)}</td>
                  <td className="max-w-md truncate pr-3 text-xs text-slate-600">{JSON.stringify(r.details)}</td>
                  <td>{r.trace_url && <a className="text-blue-700 underline" href={r.trace_url} target="_blank" rel="noreferrer">Trace</a>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && !error && <p className="py-4 text-sm text-slate-600">No events yet.</p>}
        </div>
      </Card>
    </>
  )
}
