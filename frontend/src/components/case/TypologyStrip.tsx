import { useState } from 'react'
import type { Case, Investigation, Report } from '../../api'
import { Badge, Button, label } from '../../ui'

const TYPOLOGIES = [
  ['account_takeover', 'Account takeover'],
  ['mule_payment', 'Mule payment'],
  ['loan_proceeds_diversion', 'Loan proceeds diversion'],
  ['staged_claim_ring', 'Staged claim ring'],
  ['verified_device_change', 'Verified device change'],
  ['established_payee', 'Established payee'],
] as const

type Result = NonNullable<Investigation['typology']>
type Proof = Result['proofs'][number]

function requires(requirement: Result['requirement']) {
  if (requirement === 'none') return 'No requirement'
  return `Requires: ${label(requirement)}`
}

const toneOf = (requirement: Result['requirement']) =>
  requirement === 'suspicious' ? 'red' : requirement === 'not_suspicious' ? 'green' : 'slate'

function Steps({ proofs, onShowEvidence }: { proofs: Proof[]; onShowEvidence: (id: string) => void }) {
  return (
    <div className="space-y-3">
      {proofs.map((proof) => (
        <div key={proof.subject + proof.account}>
          <p className="mb-1 flex items-center justify-between gap-2 text-sm">
            <span className="text-slate-600">On {proof.account}</span>
            {proof.evidence_id && <button type="button" className="text-xs text-blue-700 underline" onClick={() => onShowEvidence(proof.evidence_id!)}>{proof.evidence_id}</button>}
          </p>
          <ol className={`space-y-1 border-l-2 pl-3 ${proof.direction === 'fraud' ? 'border-red-600' : 'border-emerald-600'}`}>
            {proof.steps.map((step) => (
              <li key={step.text} className="flex items-baseline justify-between gap-3 text-sm">
                <span>✓ {step.text}{step.quote && <span className="text-slate-500"> ("{step.quote}")</span>}</span>
                {step.record && <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-800">{step.record}</span>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}

function Board({ result, onShowEvidence }: { result: Result; onShowEvidence: (id: string) => void }) {
  const first = result.proofs[0]?.typology ?? result.near[0]?.typology ?? TYPOLOGIES[0][0]
  const [picked, setPicked] = useState<string>(first)
  const proofs = result.proofs.filter((p) => p.typology === picked)
  const near = result.near.filter((n) => n.typology === picked)

  return (
    <div className="grid gap-4 md:grid-cols-[17rem_1fr]">
      <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 text-sm">
        {TYPOLOGIES.map(([id, name]) => {
          const proved = result.proofs.find((p) => p.typology === id)
          return (
            <li key={id}>
              <button type="button" onClick={() => setPicked(id)} aria-pressed={picked === id} className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left ${picked === id ? 'bg-slate-100' : ''}`}>
                <span>{name}</span>
                {proved
                  ? <Badge tone={proved.direction === 'fraud' ? 'red' : 'green'}>Proved</Badge>
                  : result.near.some((n) => n.typology === id)
                    ? <Badge tone="amber">Nearly</Badge>
                    : <span className="text-xs text-slate-400">Not proved</span>}
              </button>
            </li>
          )
        })}
      </ul>
      <div className="min-w-0 text-sm">
        <p className="mb-2 font-medium">{TYPOLOGIES.find(([id]) => id === picked)?.[1]}</p>
        {proofs.length > 0 && <Steps proofs={proofs} onShowEvidence={onShowEvidence} />}
        {proofs.length === 0 && near.length > 0 && <ul className="space-y-1">{near.map((n) => <li key={n.account}>{n.account} is missing {n.missing}.</li>)}</ul>}
        {proofs.length === 0 && near.length === 0 && <p className="text-slate-600">The records show nothing that fits this Typology.</p>}
      </div>
    </div>
  )
}

export default function TypologyStrip({
  result,
  report,
  item,
  onShowEvidence,
}: {
  result: Result
  report: Report | null
  item: Case
  onShowEvidence: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const names = [...new Map(result.proofs.map((p) => [p.typology, p])).values()]
  const mismatch = report?.verification === 'unverified' && report.verification_errors.some((e) => e.startsWith('Typology'))
  const proved = result.proofs.some((p) => p.direction === 'fraud')
  const lowered = proved && item.risk_level !== 'high' && item.original_risk_level !== item.risk_level

  return (
    <section aria-label="Typology check" className="rounded-lg border border-slate-200 bg-white px-4 py-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">Typology check</span>
        <Badge tone={toneOf(result.requirement)}>{requires(result.requirement)}</Badge>
        {names.map((p) => <Badge key={p.typology} tone={p.direction === 'fraud' ? 'red' : 'green'}>{p.name}</Badge>)}
        {mismatch && report?.assessment && <Badge tone="amber">Agent said: {label(report.assessment)}</Badge>}
        {lowered && <Badge tone="amber">Proved fraud, classified {label(item.risk_level)} by an Analyst</Badge>}
        {result.near.length > 0 && <span className="text-slate-500">{result.near.length} nearly proved</span>}
        <span className="ml-auto"><Button onClick={() => setOpen((v) => !v)}>{open ? 'Hide proof' : 'Show proof'}</Button></span>
      </div>
      {open && (
        <div className="mt-2 max-h-80 space-y-3 overflow-y-auto border-t border-slate-100 pt-2">
          {mismatch && <p className="rounded-md bg-red-50 p-2 text-sm text-red-800">The agent's report disagrees with this proof after its one retry, so it's Unverified and your Decision needs a note.</p>}
          <Board result={result} onShowEvidence={onShowEvidence} />
        </div>
      )}
    </section>
  )
}
