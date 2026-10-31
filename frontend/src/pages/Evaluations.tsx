import { useEffect, useState } from 'react'
import { ApiError, api, type EvalRun } from '../api'
import { Badge, Card, ErrorNote, Stat, label, when } from '../ui'

const percent = (value: number) => `${Math.round(value * 100)}%`

export default function Evaluations() {
  const [run, setRun] = useState<EvalRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.evals().then(setRun).catch((e) => setError(e instanceof ApiError && e.status === 404 ? 'No eval run has been saved yet.' : e.message))
  }, [])

  return (
    <>
      <h1 className="text-xl font-semibold">Evaluations</h1>
      <ErrorNote message={error} />
      {run && (
        <>
          <p className="text-sm text-slate-600">
            Saved run from {when(run.run_at)}, commit {run.commit}, model {run.model}, estimated cost ₹{run.estimated_cost_inr}.
          </p>
          <p className="rounded-md bg-slate-100 p-3 text-sm">{run.notice}</p>
          {run.detection && (
            <>
              <div className="grid gap-3 sm:grid-cols-4">
                <Stat label="Precision" value={percent(run.detection.precision)} />
                <Stat label="Recall" value={percent(run.detection.recall)} />
                <Stat label="False positives" value={run.detection.false_positives} />
                <Stat label="Missed fraud" value={run.detection.false_negatives} />
              </div>
              <Card title="What detection misses">
                <ul className="space-y-1 text-sm">
                  {Object.entries(run.detection.misses_by_story).map(([story, count]) => (
                    <li key={story} className="flex justify-between"><span>{label(story)}</span><span className="tabular-nums">{count}</span></li>
                  ))}
                </ul>
              </Card>
            </>
          )}
          <Card title="Agent">
            <ul className="space-y-1 text-sm">
              {run.scenarios.map((s) => (
                <li key={s.name} className="flex items-center justify-between gap-3">
                  <span>{label(s.name)}: {s.correct} of {s.runs} correct (gate {s.gate} of 10)</span>
                  <Badge tone={s.passed ? 'green' : 'red'}>{s.passed ? 'Passed' : 'Below gate'}</Badge>
                </li>
              ))}
              <li>Held-out Alerts: {run.held_out_correct} of {run.held_out_total} correct</li>
            </ul>
          </Card>
          <Card title="Security">
            <ul className="space-y-1 text-sm">
              <li>Prompt injection: {run.injection_passed} of {run.injection_total} passed</li>
              <li>Out-of-scope denials: {run.denials_passed} of {run.denials_total} passed</li>
            </ul>
          </Card>
          <Card title={`Failed cases (${run.failures.length})`}>
            <ul className="space-y-1.5 text-sm">
              {run.failures.map((f) => (
                <li key={f.case_id}>
                  <strong>{f.case_id}</strong> {f.failures.join(' ')}{' '}
                  {f.trace_url && <a className="text-blue-700 underline" href={f.trace_url} target="_blank" rel="noreferrer">Trace</a>}
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </>
  )
}
