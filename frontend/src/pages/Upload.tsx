import { useState } from 'react'
import { api, type UploadResult } from '../api'
import { Button, Card, ErrorNote, Stat, inputClass, label } from '../ui'
import { Button as ShadButton } from '@/components/ui/button'
import { cn } from 'cn'
import { useFileUpload } from '@/hooks/use-file-upload'
import { UploadIcon, FileIcon, XIcon } from 'lucide-react'

const DATASETS = ['customers', 'transactions', 'logins', 'loan_applications', 'account_events', 'policies', 'claims']

export default function Upload() {
  const [dataset, setDataset] = useState('transactions')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  const [{ files, isDragging, errors }, { removeFile, clearFiles, handleDragEnter, handleDragLeave, handleDragOver, handleDrop, openFileDialog, getInputProps }] = useFileUpload({
    maxFiles: 1,
    maxSize: 50 * 1024 * 1024,
    accept: '.csv,.xlsx,.json',
    multiple: false,
    onFilesChange: (changed) => {
      const next = changed[0]?.file
      setFile(next instanceof File ? next : null)
    },
  })

  async function upload() {
    if (!file) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.upload(dataset, file))
      clearFiles()
      setFile(null)
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
          <a className="text-sm text-blue-700 underline" href={`/api/ingest/templates/${dataset}`}>Download template</a>
        </div>

        <div
          className={cn(
            'mt-4 relative rounded-lg border border-dashed p-8 text-center transition-colors',
            isDragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-muted-foreground/50'
          )}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <input {...getInputProps()} className="sr-only" />
          <div className="flex flex-col items-center gap-4">
            <div className={cn('flex h-16 w-16 items-center justify-center rounded-full', isDragging ? 'bg-primary/10' : 'bg-muted')}>
              <UploadIcon className={cn('h-5 w-5', isDragging ? 'text-primary' : 'text-muted-foreground')} />
            </div>
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">Drop a file here</h3>
              <p className="text-muted-foreground text-sm">or click to browse</p>
              <p className="text-muted-foreground text-xs">CSV, Excel or JSON (max 50 MB)</p>
            </div>
            <Button onClick={openFileDialog}>Select file</Button>
          </div>
        </div>

        {files.length > 0 && (
          <div className="mt-4 flex items-center justify-between rounded-md border border-slate-200 p-3">
            <div className="flex items-center gap-3">
              <FileIcon className="h-5 w-5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">{files[0].file.name}</p>
                <p className="text-xs text-muted-foreground">{files[0].file.size} bytes</p>
              </div>
            </div>
            <ShadButton variant="ghost" size="icon" onClick={() => { removeFile(files[0].id); setFile(null) }}>
              <XIcon className="h-4 w-4" />
            </ShadButton>
          </div>
        )}

        {errors.length > 0 && (
          <p className="mt-3 text-sm text-red-800">{errors.join(' ')}</p>
        )}

        <div className="mt-4 flex items-center gap-3">
          <Button primary disabled={!file || busy} onClick={upload}>Upload</Button>
        </div>
        <p className="mt-3 text-sm text-slate-600">Valid rows load, and every invalid row is listed with its reason.</p>
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
