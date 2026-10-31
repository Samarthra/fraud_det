import { useCallback, useEffect, useState } from 'react'
import { ApiError, api, type EvalRun, type EvalStatus } from '../api'
import { Badge, Button, Card, ErrorNote, Stat, label, when } from '../ui'

const POLL_MS = 3000
const percent = (value: number) => `${Math.round(value * 100)}%`

function TypologyCard({ run }: { run: EvalRun }) {
  const t = run.typology!
  const base = t.baseline
  const score = (name: string) => run.scenarios.find((s) => s.name === name)
  const rows: [string, string | number | undefined, string | number][] = base
    ? [
        ['False positive correct', base.false_positive, `${score('false_positive')?.correct ?? 0} of ${score('false_positive')?.runs ?? 0}`],
        ['Takeover correct', base.account_takeover, `${score('account_takeover')?.correct ?? 0} of ${score('account_takeover')?.runs ?? 0}`],
        ['Held-out correct', `${base.held_out_correct} of ${base.held_out_total}`, `${run.held_out_correct} of ${run.held_out_total}`],
        ['Injection passed', `${base.injection_passed} of ${base.injection_total}`, `${run.injection_passed} of ${run.injection_total}`],
        ['Model calls per Investigation', base.calls_per_investigation, t.calls_per_investigation],
        ['Seconds per Investigation', base.seconds_per_investigation, t.seconds_per_investigation],
      ]
    : []
  return (
    <Card title="Typology check" tooltip="Whether the check earned its place, compared with a run before it existed.">
      {t.keep !== null && (
        <div className="mb-3 flex items-center gap-2 text-sm">
          <Badge tone={t.keep ? 'green' : 'red'}>{t.keep ? 'Meets the keep bar' : 'Below the keep bar'}</Badge>
          {t.keep_reasons.map((r) => <span key={r} className="text-slate-600">{r}</span>)}
        </div>
      )}
      {rows.length > 0 && (
        <table className="mb-3 w-full text-left text-sm">
          <thead className="text-slate-500"><tr><th className="py-1">Measure</th><th>Before</th><th>After</th></tr></thead>
          <tbody>{rows.map(([name, before, after]) => <tr key={name} className="border-t border-slate-100"><td className="py-1">{name}</td><td className="tabular-nums">{before}</td><td className="tabular-nums">{after}</td></tr>)}</tbody>
        </table>
      )}
      <ul className="space-y-1 text-sm">
        <li>Retries fired: {t.retries}</li>
        <li>Reports left Unverified by a mismatch: {t.unverified_by_mismatch}</li>
        <li>Model calls: {t.model_calls}. Cost above is an estimate, not a measurement.</li>
        {t.reader && <li>Text reader: LLM {t.reader.llm.correct} of {t.reader.llm.total}, phrase match {t.reader.phrase_match.correct} of {t.reader.phrase_match.total}</li>}
      </ul>
      <h3 className="mb-1 mt-3 text-xs font-semibold text-slate-500">No-LLM sweep, by story</h3>
      <table className="w-full text-left text-sm">
        <thead className="text-slate-500"><tr><th className="py-1">Story</th><th>Truth</th><th>Alerts</th><th>Requires suspicious</th><th>Requires not suspicious</th><th>No requirement</th></tr></thead>
        <tbody>
          {Object.entries(t.sweep.stories).map(([story, row]) => (
            <tr key={story} className="border-t border-slate-100">
              <td className="py-1">{label(story)}</td><td>{row.fraud ? 'Fraud' : 'Benign'}</td><td className="tabular-nums">{row.alerts}</td>
              <td className="tabular-nums">{row.suspicious}</td><td className="tabular-nums">{row.not_suspicious}</td><td className="tabular-nums">{row.none}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">{t.sweep.wrong.length} benign Alert(s) required suspicious. Each sits on an account with fraud proved in the same 7 days, so read them with that in mind.</p>
    </Card>
  )
}

export default function Evaluations() {
  const [run, setRun] = useState<EvalRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [status, setStatus] = useState<EvalStatus | null>(null)
  const [wasRunning, setWasRunning] = useState(false)
  const [pollFailed, setPollFailed] = useState(false)

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
        try {
          const current = await api.evalStatus()
          if (stop) return
          setStatus(current)
          setPollFailed(false)
          setWasRunning((before) => {
            if (before && !current.running) loadRun()
            return current.running
          })
        } catch {
          if (!stop) setPollFailed(true) // keep trying, the run carries on regardless
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_MS))
      }
    }
    poll()
    return () => {
      stop = true
    }
  }, [loadRun])

  async function start() {
    if (!window.confirm('Run all evals? This makes live Sarvam calls, takes about 25 minutes, and costs about ₹12.')) return
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
        <Card title="Eval in progress" tooltip="Live progress of the eval run.">
          <p className="text-sm text-slate-600">
            {status?.total ? `${status.done} of ${status.total} cases done, now on ${status.current}` : 'Starting up. Progress appears once the first case begins.'}
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded bg-slate-200">
            <div className="h-full bg-blue-700" style={{ width: `${share}%` }} />
          </div>
          {pollFailed && <p className="mt-2 text-sm text-amber-800">Lost contact with the server. Retrying…</p>}
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
                <Stat label="Precision" value={percent(run.detection.precision)} tooltip="Share of flagged cases that are fraud." />
                <Stat label="Recall" value={percent(run.detection.recall)} tooltip="Share of fraud cases caught." />
                <Stat label="False positives" value={run.detection.false_positives} tooltip="Non-fraud cases flagged." />
                <Stat label="Missed fraud" value={run.detection.false_negatives} tooltip="Fraud cases not flagged." />
              </div>
              <Card title="What detection misses" tooltip="Fraud stories detection failed to catch.">
                <ul className="space-y-1 text-sm">
                  {Object.entries(run.detection.misses_by_story).map(([story, count]) => (
                    <li key={story} className="flex justify-between"><span>{label(story)}</span><span className="tabular-nums">{count}</span></li>
                  ))}
                </ul>
              </Card>
            </>
          )}
          <Card title="Agent" tooltip="Scenario pass rates for the investigation agent.">
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
          {run.typology && <TypologyCard run={run} />}
          <Card title="Security" tooltip="Prompt injection and out-of-scope denial results.">
            <ul className="space-y-1 text-sm">
              <li>Prompt injection: {run.injection_passed} of {run.injection_total} passed</li>
              <li>Out-of-scope denials: {run.denials_passed} of {run.denials_total} passed</li>
            </ul>
          </Card>
          <Card title={`Failed cases (${run.failures.length})`} tooltip="Cases that failed eval checks.">
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
