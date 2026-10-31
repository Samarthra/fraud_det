import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type CaseDetail, type DecisionValue, type Evidence, type Investigation, type Step } from '../api'
import { Badge, Button, Card, ErrorNote, Risk, inputClass, label, when } from '../ui'

const REVEAL_MS = 700
const POLL_MS = 500
const DECISIONS: DecisionValue[] = ['requires_investigation', 'false_positive', 'confirmed_fraud', 'escalated']

function useSteps(investigationId: string | null, tick: number) {
  const [queue, setQueue] = useState<Step[]>([])
  const [shown, setShown] = useState(0)
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const after = useRef(0)
  const started = useRef<string | null>(null)

  useEffect(() => {
    if (!investigationId) return
    if (started.current !== investigationId) {
      started.current = investigationId
      after.current = 0
      setQueue([])
      setShown(0)
    }
    let stop = false
    async function poll() {
      while (!stop) {
        const [steps, current] = await Promise.all([
          api.steps(investigationId!, after.current),
          api.investigation(investigationId!),
        ])
        if (stop) return
        if (steps.length) {
          after.current = steps[steps.length - 1].seq
          setQueue((q) => [...q, ...steps])
        }
        setInvestigation(current)
        const answering = current.follow_ups.some((f) => f.answer === null)
        if (current.status === 'complete' && !answering) return
        await new Promise((resolve) => setTimeout(resolve, POLL_MS))
      }
    }
    poll().catch(() => undefined)
    return () => {
      stop = true
    }
  }, [investigationId, tick])

  useEffect(() => {
    if (shown >= queue.length) return
    const timer = setTimeout(() => setShown((n) => n + 1), REVEAL_MS)
    return () => clearTimeout(timer)
  }, [shown, queue.length])

  const refresh = useCallback(() => {
    if (investigationId) api.investigation(investigationId).then(setInvestigation)
  }, [investigationId])

  const finished = investigation?.status === 'complete' && shown >= queue.length
  return { steps: queue.slice(0, shown), investigation, finished, refresh }
}

function EvidenceRow({ evidence, open }: { evidence: Evidence; open: boolean }) {
  return (
    <details id={evidence.id} open={open} className="border-t border-slate-100 py-1.5 text-sm">
      <summary className="cursor-pointer">
        <span className="font-medium">{evidence.id}</span> {label(evidence.kind)} {evidence.source_ref}
      </summary>
      <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(evidence.data, null, 2)}</pre>
    </details>
  )
}

export default function CasePage({ id }: { id: string }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [investigationId, setInvestigationId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [denied, setDenied] = useState(false)
  const [decision, setDecision] = useState<DecisionValue>('requires_investigation')
  const [note, setNote] = useState('')
  const [question, setQuestion] = useState('')
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const { steps, investigation, finished, refresh } = useSteps(investigationId, tick)

  const load = useCallback(() => {
    api.caseDetail(id)
      .then((d) => {
        setDetail(d)
        setInvestigationId(d.case.investigation_id ?? null)
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 403) setDenied(true)
        else setError(e.message)
      })
  }, [id])

  useEffect(load, [load])

  async function act(work: () => Promise<unknown>) {
    setError(null)
    try {
      await work()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (denied) return <ErrorNote message={`${id} is outside this Analyst's Portfolio. This attempt has been audited.`} />
  if (!detail) return <ErrorNote message={error} />
  const { case: item, alert } = detail
  const report = finished ? investigation?.report : null
  const unverified = report?.verification === 'unverified'
  const running = Boolean(investigationId) && !finished
  const replay = investigation?.is_replay

  return (
    <>
      {replay && (
        <p className="rounded-md bg-amber-100 p-3 text-sm font-medium text-amber-900">
          Replay of a saved real Investigation, captured at {when(investigation!.replay_captured_at!)}, no live model calls
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold">{item.id}</h1>
        <Risk level={item.risk_level} />
        <Badge>{label(item.status)}</Badge>
        {replay && <Badge tone="amber">Replay</Badge>}
        <span className="text-sm text-slate-600">{label(item.category)} on {item.account_id}, customer {item.customer_id}</span>
      </div>
      <ErrorNote message={error} />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title={`Alert ${alert.id}: score ${alert.score}`}>
            <ul className="space-y-1 text-sm">
              {alert.rule_hits.map((h) => (
                <li key={h.rule} className="flex justify-between gap-4"><span>{h.reason}</span><span className="tabular-nums text-slate-500">+{h.points}</span></li>
              ))}
            </ul>
            {item.supporting_records.map((r) => (
              <details key={r.source_ref} className="mt-2 text-sm">
                <summary className="cursor-pointer">{label(r.kind)} {r.source_ref}</summary>
                <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(r.data, null, 2)}</pre>
              </details>
            ))}
          </Card>

          {!investigationId && (
            <Card title="Investigation">
              <div className="flex flex-wrap gap-2">
                <Button primary onClick={() => act(async () => setInvestigationId((await api.investigate(id, false)).investigation_id))}>Investigate</Button>
                {detail.replay_available && <Button onClick={() => act(async () => setInvestigationId((await api.investigate(id, true)).investigation_id))}>Replay</Button>}
              </div>
            </Card>
          )}

          {investigationId && (
            <Card title="Agent steps" action={running ? <span className="text-sm text-slate-500">Working…</span> : undefined}>
              <ol className="space-y-1 text-sm">
                {steps.map((s) => (
                  <li key={s.seq} className="flex items-start gap-3">
                    <span className="w-24 shrink-0 text-xs text-slate-500">{label(s.stage)}</span>
                    <span className={s.type === 'denied' ? 'font-medium text-red-700' : ''}>{s.summary}</span>
                    {s.evidence_ids.length > 0 && <span className="text-xs text-slate-500">{s.evidence_ids.join(', ')}</span>}
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {report && (
            <Card
              title="Report"
              action={
                <div className="flex items-center gap-2">
                  <Badge tone={unverified ? 'red' : 'green'}>{unverified ? 'Unverified' : 'Verified'}</Badge>
                  {investigation?.trace_url && <a className="text-sm text-blue-700 underline" href={investigation.trace_url} target="_blank" rel="noreferrer">Trace</a>}
                </div>
              }
            >
              {report.assessment && <p className="mb-2 text-sm"><span className="text-slate-500">Assessment:</span> <strong>{label(report.assessment)}</strong></p>}
              <p className="text-sm">{report.summary}</p>
              {unverified && report.verification_errors.length > 0 && (
                <ul className="mt-2 list-disc rounded-md bg-red-50 p-3 pl-6 text-sm text-red-800">
                  {report.verification_errors.map((e) => <li key={e}>{e}</li>)}
                </ul>
              )}
              {report.findings.length > 0 && (
                <>
                  <h3 className="mt-3 text-xs font-semibold text-slate-500">Findings</h3>
                  <ul className="mt-1 space-y-1.5 text-sm">
                    {report.findings.map((f) => (
                      <li key={f.statement}>
                        {f.statement}{' '}
                        {f.evidence_ids.map((e) => (
                          <button key={e} type="button" className="ml-1 text-xs text-blue-700 underline" onClick={() => { setOpenEvidence(e); document.getElementById(e)?.scrollIntoView({ behavior: 'smooth', block: 'center' }) }}>{e}</button>
                        ))}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {report.limitations.length > 0 && (
                <>
                  <h3 className="mt-3 text-xs font-semibold text-slate-500">Limitations</h3>
                  <ul className="mt-1 list-disc pl-5 text-sm">{report.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
                </>
              )}
              {report.recommended_actions.length > 0 && (
                <p className="mt-3 text-sm"><span className="text-slate-500">Recommended, not carried out:</span> {report.recommended_actions.map(label).join(', ')}</p>
              )}
            </Card>
          )}

          {report && investigation && investigation.evidence.length > 0 && (
            <Card title="Evidence">
              {investigation.evidence.map((e) => <EvidenceRow key={e.id} evidence={e} open={openEvidence === e.id} />)}
            </Card>
          )}

          {report && investigation && !replay && (
            <Card title="Follow-ups">
              <ul className="mb-3 space-y-2 text-sm">
                {investigation.follow_ups.map((f) => (
                  <li key={f.id}>
                    <p className="font-medium">{f.question}</p>
                    <p>{f.answer ?? 'Working…'}</p>
                    {f.verification && <Badge tone={f.verification === 'verified' ? 'green' : 'red'}>{label(f.verification)}</Badge>}
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <input aria-label="Question" className={`${inputClass} flex-1`} placeholder="Ask about this Investigation" value={question} onChange={(e) => setQuestion(e.target.value)} />
                <Button disabled={!question.trim()} onClick={() => act(async () => { await api.followUp(investigation.id, question); setQuestion(''); setTick((t) => t + 1) })}>Ask</Button>
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title="Decision">
            <div className="space-y-2">
              <select aria-label="Decision" className={`${inputClass} w-full`} value={decision} onChange={(e) => setDecision(e.target.value as DecisionValue)}>
                {DECISIONS.map((d) => <option key={d} value={d}>{label(d)}</option>)}
              </select>
              <textarea aria-label="Note" className={`${inputClass} w-full`} rows={3} placeholder={unverified ? 'A note is required for an Unverified report' : 'Note'} value={note} onChange={(e) => setNote(e.target.value)} />
              <Button primary onClick={() => act(async () => { await api.decide(id, decision, note); setNote(''); load(); refresh() })}>Record Decision</Button>
              <p className="text-xs text-slate-500">Recording a Decision does not carry out any action. The original Alert never changes.</p>
            </div>
            {item.decisions.length > 0 && (
              <>
                <h3 className="mt-3 text-xs font-semibold text-slate-500">History</h3>
                <ol className="mt-1 space-y-1.5 text-sm">
                  {[...item.decisions].reverse().map((d) => (
                    <li key={d.at + d.decision}>
                      <strong>{label(d.decision)}</strong>
                      <span className="text-xs text-slate-500"> {d.analyst}, {when(d.at)}</span>
                      {d.note && <p className="text-slate-700">{d.note}</p>}
                    </li>
                  ))}
                </ol>
              </>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
