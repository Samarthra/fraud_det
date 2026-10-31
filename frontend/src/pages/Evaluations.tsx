import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type EvalRun, type EvalStatus } from '../api'
import { Badge, Button, Card, ErrorNote, Stat, label, when } from '../ui'

const POLL_MS = 3000
const percent = (value: number) => `${Math.round(value * 100)}%`

export default function Evaluations() {
  const [run, setRun] = useState<EvalRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [status, setStatus] = useState<EvalStatus | null>(null)
  const [wasRunning, setWasRunning] = useState(false)

  const loadRun = useCallback(() => {
    api.evals()
      .then((r) => {
        setRun(r)
        setError(null)
      })
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? 'No eval run has been saved yet.' : e.message))
  }, [])

  useEffect(loadRun, [loadRun])

  useEffect(() => {
    let stop = false
    async function poll() {
      while (!stop) {
        const current = await api.evalStatus()
        if (stop) return
        setStatus(current)
        setWasRunning((before) => {
          if (before && !current.running) loadRun()
          return current.running
        })
        await new Promise((resolve) => setTimeout(resolve, POLL_MS))
      }
    }
    poll().catch(() => undefined)
    return () => {
      stop = true
    }
  }, [loadRun])

  async function start() {
    if (!window.confirm('Run all evals? This makes live Sarvam calls, takes about 25 minutes, and costs about ₹10.')) return
    try {
      await api.runEvals()
      setWasRunning(true)
      setStatus(await api.evalStatus())
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const running = Boolean(status?.running || wasRunning)
  const share = status && status.total ? Math.round((status.done / status.total) * 100) : 0

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Evaluations</h1>
        <Button primary disabled={running} onClick={start}>{running ? 'Eval running…' : 'Run evals'}</Button>
      </div>
      {running && (
        <Card title="Eval in progress">
          <p className="text-sm text-slate-600">
            {status?.total ? `${status.done} of ${status.total} cases done, now on ${status.current}` : 'Starting up. Progress appears once the first case begins.'}
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded bg-slate-200">
            <div className="h-full bg-blue-700" style={{ width: `${share}%` }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">You can leave this page. The run continues, and the results below update when it finishes.</p>
        </Card>
      )}
      {!running && status?.last_error && <ErrorNote message={`The last eval run failed: ${status.last_error}`} />}
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
