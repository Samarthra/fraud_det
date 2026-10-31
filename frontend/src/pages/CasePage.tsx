import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type CaseDetail, type DecisionValue } from '../api'
import ActivityPanel from '../components/case/ActivityPanel'
import AlertTab from '../components/case/AlertTab'
import DecisionDrawer from '../components/case/DecisionDrawer'
import EvidenceTab from '../components/case/EvidenceTab'
import ReportTab from '../components/case/ReportTab'
import { useSteps } from '../components/case/useSteps'
import EntityGraph from '../components/EntityGraph'
import { Badge, Button, ErrorNote, Risk, label, when } from '../ui'

type Tab = 'report' | 'evidence' | 'graph' | 'alert'

export default function CasePage({ id }: { id: string }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [investigationId, setInvestigationId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [denied, setDenied] = useState(false)
  const [tick, setTick] = useState(0)
  const [tab, setTab] = useState<Tab>('alert')
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [drawer, setDrawer] = useState(false)
  const chosenTab = useRef(false)
  const { steps, investigation, finished, refresh, pollFailed } = useSteps(investigationId, tick)

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

  // The report arriving is the payoff, unless the Analyst has chosen something else to read.
  useEffect(() => {
    if (!finished) return
    load()
    if (!chosenTab.current) setTab('report')
  }, [finished, load])

  async function act(work: () => Promise<unknown>) {
    setError(null)
    try {
      await work()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  function pick(next: Tab) {
    chosenTab.current = true
    setTab(next)
  }

  function start(replay: boolean) {
    chosenTab.current = false
    act(async () => setInvestigationId((await api.investigate(id, replay)).investigation_id))
  }

  function showEvidence(evidenceId: string) {
    setOpenEvidence(evidenceId)
    pick('evidence')
  }

  async function decide(decision: DecisionValue, note: string) {
    await api.decide(id, decision, note)
    load()
    refresh()
  }

  if (denied) return <ErrorNote message={`${id} is outside this Analyst's Portfolio. This attempt has been audited.`} />
  if (!detail) return <ErrorNote message={error} />
  const { case: item, alert } = detail
  const report = finished ? investigation?.report ?? null : null
  const running = Boolean(investigationId) && !finished
  const replay = Boolean(investigation?.is_replay)
  const current = item.decisions.length ? item.decisions[item.decisions.length - 1] : null
  const evidence = investigation?.evidence ?? []
  const TABS: [Tab, string][] = [
    ['report', running ? 'Report (drafting)' : 'Report'],
    ['evidence', `Evidence (${evidence.length})`],
    ['graph', 'Graph'],
    ['alert', 'Alert'],
  ]

  return (
    <div className="flex flex-col gap-3 lg:h-[calc(100vh-5.5rem)]">
      {replay && (
        <p className="rounded-md bg-amber-100 p-2 text-sm font-medium text-amber-900">
          Replay of a saved real Investigation, captured at {when(investigation!.replay_captured_at!)}, no live model calls
        </p>
      )}
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5">
        <h1 className="text-lg font-semibold">{item.id}</h1>
        <Risk level={item.risk_level} />
        <Badge>{label(running ? 'investigating' : item.status)}</Badge>
        {replay && <Badge tone="amber">Replay</Badge>}
        <span className="text-sm text-slate-600">{label(item.category)} on {item.account_id}, customer {item.customer_id}</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-slate-600">
            Decision: <strong className="text-slate-900">{current ? label(current.decision) : 'None yet'}</strong>
          </span>
          <Button primary onClick={() => setDrawer(true)}>Record Decision</Button>
        </div>
      </header>
      <ErrorNote message={error} />

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[23rem_1fr]">
        <ActivityPanel
          investigationId={investigationId}
          investigation={investigation}
          steps={steps}
          running={running}
          finished={finished}
          pollFailed={pollFailed}
          replayAvailable={detail.replay_available}
          onStart={start}
          onShowEvidence={showEvidence}
          onAsk={(question) =>
            act(async () => {
              await api.followUp(investigation!.id, question)
              setTick((t) => t + 1)
            })
          }
        />

        <section className="flex min-h-[30rem] min-w-0 flex-col rounded-lg border border-slate-200 bg-white">
          <div role="tablist" className="flex gap-1 border-b border-slate-200 px-3 pt-2">
            {TABS.map(([key, text]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => pick(key)}
                className={`-mb-px rounded-t-md border-b-2 px-3 py-2 text-sm ${tab === key ? 'border-blue-700 font-medium text-blue-800' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
              >
                {text}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {tab === 'report' && (
              <ReportTab
                report={report}
                running={running}
                traceUrl={investigation?.trace_url ?? null}
                onShowEvidence={showEvidence}
                onRetry={() => start(false)}
              />
            )}
            {tab === 'evidence' && (
              <EvidenceTab
                evidence={evidence}
                open={openEvidence}
                onBack={report ? () => pick('report') : undefined}
              />
            )}
            {tab === 'graph' && <EntityGraph key={alert.id} alert={alert} />}
            {tab === 'alert' && <AlertTab alert={alert} records={item.supporting_records} />}
          </div>
        </section>
      </div>

      {drawer && (
        <DecisionDrawer
          decisions={item.decisions}
          unverified={report?.verification === 'unverified'}
          onDecide={decide}
          onClose={() => setDrawer(false)}
        />
      )}
    </div>
  )
}
