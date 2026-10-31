import { useEffect, useRef, useState } from 'react'
import type { Investigation, Step } from '../../api'
import { Badge, Button, inputClass, label } from '../../ui'

const STAGES = ['triage', 'evidence', 'typology', 'synthesis', 'verification', 'report'] as const

type Stage = (typeof STAGES)[number]
type Status = 'waiting' | 'running' | 'done' | 'problem'

function statusOf(stage: Stage, steps: Step[], all: Step[], running: boolean): Status {
  if (steps.length === 0) return 'waiting'
  if (stage === 'verification' && steps[steps.length - 1].summary.includes('problem')) return 'problem'
  const later = STAGES.indexOf(all[all.length - 1].stage as Stage) > STAGES.indexOf(stage)
  return running && !later ? 'running' : 'done'
}

function summaryOf(stage: Stage, steps: Step[]) {
  if (stage === 'evidence') {
    const tools = steps.filter((s) => s.type === 'tool_call').length
    const records = new Set(steps.flatMap((s) => s.evidence_ids)).size
    return `${tools} tools, ${records} records`
  }
  return steps[steps.length - 1]?.summary ?? ''
}

const DOT: Record<Status, string> = {
  waiting: 'bg-slate-300',
  running: 'bg-blue-600 animate-pulse',
  done: 'bg-emerald-600',
  problem: 'bg-amber-500',
}

function StageRow({ stage, steps, all, running }: { stage: Stage; steps: Step[]; all: Step[]; running: boolean }) {
  const status = statusOf(stage, steps, all, running)
  const [override, setOverride] = useState<boolean | null>(null)
  const open = override ?? status === 'running'
  const denied = steps.filter((s) => s.type === 'denied')
  return (
    <li className="relative pl-5">
      <span className={`absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full ${DOT[status]}`} />
      <button
        type="button"
        disabled={steps.length === 0}
        aria-expanded={open}
        onClick={() => setOverride(!open)}
        className="flex w-full items-baseline justify-between gap-2 text-left text-sm disabled:cursor-default"
      >
        <span className={`font-medium ${status === 'waiting' ? 'text-slate-400' : 'text-slate-800'}`}>{label(stage)}</span>
        <span className="truncate text-xs text-slate-500">{status === 'running' ? 'Running…' : summaryOf(stage, steps)}</span>
      </button>
      {!open && denied.map((s) => <p key={s.seq} className="mt-0.5 text-xs font-medium text-red-700">{s.summary}</p>)}
      {open && (
        <ol className="mt-1 space-y-0.5 border-l border-slate-200 pl-2">
          {steps.map((s) => (
            <li key={s.seq} className="flex items-start justify-between gap-2 text-xs">
              <span className={s.type === 'denied' ? 'font-medium text-red-700' : 'text-slate-600'}>{s.summary}</span>
              {s.evidence_ids.length > 0 && <span className="shrink-0 text-slate-400">{s.evidence_ids.length === 1 ? s.evidence_ids[0] : `${s.evidence_ids.length} records`}</span>}
            </li>
          ))}
        </ol>
      )}
    </li>
  )
}

export default function ActivityPanel({
  investigationId,
  investigation,
  steps,
  running,
  finished,
  pollFailed,
  replayAvailable,
  onStart,
  onShowEvidence,
  onAsk,
}: {
  investigationId: string | null
  investigation: Investigation | null
  steps: Step[]
  running: boolean
  finished: boolean
  pollFailed: boolean
  replayAvailable: boolean
  onStart: (replay: boolean) => void
  onShowEvidence: (id: string) => void
  onAsk: (question: string) => void
}) {
  const [question, setQuestion] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  const followUps = investigation?.follow_ups ?? []
  const answering = followUps.some((f) => f.answer === null)
  const lastAnswer = followUps[followUps.length - 1]?.answer
  const replay = Boolean(investigation?.is_replay)
  const canAsk = finished && Boolean(investigation?.report) && !replay && !answering

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [steps.length, followUps.length, lastAnswer])

  function ask() {
    if (!question.trim() || !canAsk) return
    onAsk(question)
    setQuestion('')
  }

  const placeholder = replay
    ? 'Follow-ups are disabled during a Replay'
    : canAsk
      ? 'Ask about this Investigation'
      : answering
        ? 'Waiting for the answer…'
        : 'Available once the report is ready'

  return (
    <section className="flex min-h-[24rem] min-w-0 flex-col rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-slate-700">Investigation</h2>
        {running && <span className="text-xs text-slate-500">{pollFailed ? 'Lost contact, retrying…' : 'Working…'}</span>}
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {!investigationId && (
          <div className="space-y-2">
            <p className="text-sm text-slate-600">The agent gathers Evidence, drafts a report, and code checks its facts.</p>
            <div className="flex flex-wrap gap-2">
              <Button primary onClick={() => onStart(false)}>Investigate</Button>
              {replayAvailable && <Button onClick={() => onStart(true)}>Replay</Button>}
            </div>
          </div>
        )}
        {investigationId && (
          <ol className="space-y-2">
            {STAGES.map((stage) => (
              <StageRow key={stage} stage={stage} steps={steps.filter((s) => s.stage === stage)} all={steps} running={running} />
            ))}
          </ol>
        )}
        {followUps.length > 0 && (
          <ul className="space-y-3 border-t border-slate-100 pt-3 text-sm">
            {followUps.map((f) => (
              <li key={f.id} className="space-y-1.5">
                <p className="ml-6 rounded-lg bg-blue-700 px-3 py-2 text-white">{f.question}</p>
                <div className="mr-6 rounded-lg bg-slate-100 px-3 py-2">
                  <p>{f.answer ?? 'Working…'}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    {f.verification && <Badge tone={f.verification === 'verified' ? 'green' : 'red'}>{label(f.verification)}</Badge>}
                    {f.evidence_ids.map((e) => (
                      <button key={e} type="button" className="text-xs text-blue-700 underline" onClick={() => onShowEvidence(e)}>{e}</button>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <div ref={bottom} />
      </div>
      <div className="flex gap-2 border-t border-slate-200 p-3">
        <input
          aria-label="Question"
          className={`${inputClass} min-w-0 flex-1`}
          placeholder={placeholder}
          disabled={!canAsk}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') ask()
          }}
        />
        <Button disabled={!canAsk || !question.trim()} onClick={ask}>Ask</Button>
      </div>
    </section>
  )
}
