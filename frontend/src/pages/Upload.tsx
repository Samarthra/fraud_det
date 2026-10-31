import { useState } from 'react'
import { api, type UploadResult } from '../api'
import { Button, Card, ErrorNote, Stat, inputClass, label } from '../ui'

const DATASETS = ['customers', 'transactions', 'logins', 'loan_applications']

export default function Upload() {
  const [dataset, setDataset] = useState('transactions')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  async function upload() {
    if (!file) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.upload(dataset, file))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function sample() {
    setBusy(true)
    setError(null)
    try {
      const r = await api.loadSample()
      setNote(r.already_loaded ? 'Sample data is already loaded.' : `Sample data loaded, with ${r.alerts_created} Alerts.`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Upload data</h1>
      <Card title="Load a file">
        <div className="flex flex-wrap items-center gap-3">
          <select aria-label="Dataset" className={inputClass} value={dataset} onChange={(e) => setDataset(e.target.value)}>
            {DATASETS.map((d) => <option key={d} value={d}>{label(d)}</option>)}
          </select>
          <input
            aria-label="File"
            type="file"
            accept=".csv,.xlsx,.json"
            className="text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button primary disabled={!file || busy} onClick={upload}>Upload</Button>
          <a className="text-sm text-blue-700 underline" href={`/api/ingest/templates/${dataset}`}>Download template</a>
        </div>
        <p className="mt-3 text-sm text-slate-600">CSV, Excel or JSON. Valid rows load, and every invalid row is listed with its reason.</p>
      </Card>
      <Card title="Sample data">
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={busy} onClick={sample}>Load sample data</Button>
          <a className="text-sm text-blue-700 underline" href="/api/demo/sample-file">Download a file with bad rows</a>
          {note && <span className="text-sm text-slate-600">{note}</span>}
        </div>
      </Card>
      <ErrorNote message={error} />
      {result && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            <Stat label="Rows read" value={result.total_rows} />
            <Stat label="Loaded" value={result.loaded} />
            <Stat label="Rejected" value={result.rejected.length} />
            <Stat label="New Alerts" value={result.alerts_created} />
          </div>
          {(result.ignored_columns.length > 0 || result.blank_rows > 0) && (
            <p className="text-sm text-slate-600">
              {result.blank_rows > 0 && `${result.blank_rows} blank rows skipped. `}
              {result.ignored_columns.length > 0 && `Ignored columns: ${result.ignored_columns.join(', ')}.`}
            </p>
          )}
          {result.rejected.length > 0 && (
            <Card title="Rejected rows">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-500"><tr><th className="py-1 pr-4">Row</th><th>Reason</th></tr></thead>
                <tbody>
                  {result.rejected.map((r) => (
                    <tr key={r.row} className="border-t border-slate-100">
                      <td className="py-1.5 pr-4 tabular-nums">{r.row}</td>
                      <td>{r.reasons.join(' ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </>
  )
}
