import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api, type CaseDetail, type DecisionValue, type EscalationTarget, type RiskLevel } from '../api'
import ActivityPanel from '../components/case/ActivityPanel'
import AlertTab from '../components/case/AlertTab'
import CaseGraph from '../components/case/CaseGraph'
import DecisionDrawer from '../components/case/DecisionDrawer'
import EvidenceTab from '../components/case/EvidenceTab'
import HistoryTab from '../components/case/HistoryTab'
import OverviewTab from '../components/case/OverviewTab'
import { ProofPrototypeBar, VariantBoard, VariantStrip, VariantTrail, proofVariant } from '../components/case/PROTOTYPE_ProofDisplay'
import ReportTab from '../components/case/ReportTab'
import TimelineTab from '../components/case/TimelineTab'
import { useSteps } from '../components/case/useSteps'
import { Badge, Button, ErrorNote, PriorityBadge, Risk, label, money, when } from '../ui'

type Tab = 'typology' | 'overview' | 'timeline' | 'graph' | 'report' | 'evidence' | 'alerts' | 'history'

export default function CasePage({ id }: { id: string }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [investigationId, setInvestigationId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [denied, setDenied] = useState(false)
  const [tick, setTick] = useState(0)
  const [tab, setTab] = useState<Tab>(proofVariant() === 'B' ? 'report' : proofVariant() === 'C' ? 'typology' : 'overview')
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [drawer, setDrawer] = useState(false)
  const chosenTab = useRef(false)
  const { steps, investigation, finished, refresh, pollFailed } = useSteps(investigationId, tick)

  const load = useCallback(() => {
    api.caseDetail(id)
      .then((d) => {
        // Alerts keep their original Case, so an old link can land on one that was consolidated.
        if (d.case.merged_into) {
          window.location.hash = `#/cases/${d.case.merged_into}`
          return
        }
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

  async function decide(decision: DecisionValue, note: string, escalateTo?: EscalationTarget) {
    await api.decide(id, decision, note, escalateTo)
    load()
    refresh()
  }

  async function reclassify(level: RiskLevel, reason: string) {
    await api.reclassify(id, level, reason)
    load()
  }

  async function separate(alertId: string, reason: string) {
    await api.separate(id, alertId, reason)
    load()
  }

  async function addNote(text: string) {
    await api.addNote(id, text)
    load()
  }

  const linkIds = useMemo(() => {
    const shared = detail?.reasons?.filter((r) => !['account', 'customer'].includes(r.kind)) ?? []
    return new Set(shared.map((r) => r.value))
  }, [detail])

  if (denied) return <ErrorNote message={`${id} is outside this Analyst's Portfolio. This attempt has been audited.`} />
  if (!detail) return <ErrorNote message={error} />
  const { case: item, alert } = detail
  const report = finished ? investigation?.report ?? null : null
  const running = Boolean(investigationId) && !finished
  const replay = Boolean(investigation?.is_replay)
  const current = item.decisions.length ? item.decisions[item.decisions.length - 1] : null
  const evidence = investigation?.evidence ?? []
  const alerts = detail.alerts?.length ? detail.alerts : [alert]
  const priority = item.priority
  const TABS: [Tab, string][] = [
    ...(proofVariant() === 'C' ? [['typology', 'Typology check'] as [Tab, string]] : []),
    ['overview', 'Overview'],
    ['timeline', 'Timeline'],
    ['graph', 'Network'],
    ['report', running ? 'AI report (drafting)' : 'AI report'],
    ['evidence', `Evidence (${evidence.length})`],
    ['alerts', `Alerts (${alerts.length})`],
    ['history', `Notes and history (${detail.history?.length ?? 0})`],
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
        {priority && <PriorityBadge band={priority.band} named />}
        <Risk level={item.risk_level} named />
        <Badge>Status: {label(running ? 'investigating' : item.status)}</Badge>
        {replay && <Badge tone="amber">Replay</Badge>}
        <span className="text-sm text-slate-600">{label(item.category)} on {item.account_id}, customer {item.customer_id}</span>
        {priority && priority.exposure > 0 && <span className="text-sm text-slate-600">{money(priority.exposure)} exposed</span>}
        {(item.products?.length ?? 0) > 1 && <Badge tone="blue">{item.products!.length} systems</Badge>}
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-slate-600">
            Decision: <strong className="text-slate-900">{current ? label(current.decision) : 'None yet'}</strong>
          </span>
          <Button onClick={() => act(() => api.downloadReport(id))}>Download report</Button>
          <Button primary onClick={() => setDrawer(true)}>Record Decision</Button>
        </div>
      </header>
      <ErrorNote message={error} />
      {proofVariant() === 'A' && <VariantStrip />}
      <ProofPrototypeBar />

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
            {tab === 'typology' && <VariantBoard />}
            {tab === 'report' && proofVariant() === 'B' && <VariantTrail />}
            {tab === 'overview' && <OverviewTab detail={detail} onReclassify={reclassify} onSeparate={separate} />}
            {tab === 'timeline' && <TimelineTab events={detail.timeline ?? []} />}
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
            {tab === 'graph' && detail.graph && <CaseGraph graph={detail.graph} linkIds={linkIds} />}
            {tab === 'alerts' && <AlertTab alerts={alerts} leadId={item.alert_id} />}
            {tab === 'history' && <HistoryTab history={detail.history ?? []} notes={detail.notes ?? []} onAddNote={addNote} />}
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
