import type { Report } from '../../api'
import { Badge, Button, label } from '../../ui'

export default function ReportTab({
  report,
  running,
  traceUrl,
  onShowEvidence,
  onRetry,
}: {
  report: Report | null
  running: boolean
  traceUrl: string | null
  onShowEvidence: (id: string) => void
  onRetry: () => void
}) {
  if (!report) {
    return (
      <p className="py-10 text-center text-sm text-slate-500">
        {running ? 'The agent is gathering Evidence and drafting the report…' : 'No report yet. Start an Investigation to create one.'}
      </p>
    )
  }
  const unverified = report.verification === 'unverified'
  const suspicious = report.assessment === 'suspicious'
  const tone = !report.assessment ? 'border-slate-300 bg-slate-50' : suspicious ? 'border-red-200 bg-red-50' : 'border-emerald-200 bg-emerald-50'

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 ${tone}`}>
        <div>
          <p className="text-xs text-slate-500">Assessment</p>
          <p className="text-lg font-semibold">{report.assessment ? label(report.assessment) : 'No assessment'}</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge tone={unverified ? 'red' : 'green'}>{unverified ? 'Unverified' : 'Verified'}</Badge>
          {traceUrl && <a className="text-sm text-blue-700 underline" href={traceUrl} target="_blank" rel="noreferrer">Trace</a>}
        </div>
      </div>
      {!report.assessment && <Button primary onClick={onRetry}>Investigate again</Button>}
      <p className="text-sm leading-relaxed">{report.summary}</p>
      {unverified && report.verification_errors.length > 0 && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">
          <p className="font-medium">Why this report is Unverified</p>
          <ul className="mt-1 list-disc pl-5">{report.verification_errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}
      {report.findings.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold text-slate-500">Findings</h3>
          <ol className="space-y-2">
            {report.findings.map((f, i) => (
              <li key={f.statement} className="flex gap-3 rounded-md border border-slate-200 p-3 text-sm">
                <span className="font-semibold text-slate-400">{i + 1}</span>
                <div className="min-w-0">
                  <p>{f.statement}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {f.evidence_ids.map((e) => (
                      <button key={e} type="button" onClick={() => onShowEvidence(e)} className="rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-800 hover:bg-blue-100">{e}</button>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
      {report.limitations.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-slate-500">Limitations</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">{report.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
      {report.recommended_actions.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-slate-500">Recommended, not carried out</h3>
          <div className="flex flex-wrap gap-1.5">{report.recommended_actions.map((a) => <Badge key={a}>{label(a)}</Badge>)}</div>
        </div>
      )}
    </div>
  )
}
