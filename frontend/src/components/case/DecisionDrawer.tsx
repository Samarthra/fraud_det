import { useEffect, useState } from 'react'
import type { Case, DecisionValue, EscalationTarget } from '../../api'
import { Button, ErrorNote, inputClass, label, when } from '../../ui'

const ACTIONS: { value: DecisionValue; text: string; hint?: string }[] = [
  { value: 'requires_investigation', text: 'Requires further investigation' },
  { value: 'false_positive', text: 'False positive', hint: 'Why is this a false positive?' },
  { value: 'information_requested', text: 'Request additional information', hint: 'What information is needed?' },
  { value: 'escalated', text: 'Escalate' },
  { value: 'hold_recommended', text: 'Recommend a temporary hold', hint: 'Why is a hold recommended?' },
  { value: 'verification_recommended', text: 'Recommend enhanced verification', hint: 'Why is verification recommended?' },
  { value: 'confirmed_fraud', text: 'Confirmed fraud' },
  { value: 'concluded', text: 'Record investigation conclusion', hint: 'Write the conclusion' },
]
const RECOMMENDATIONS: DecisionValue[] = ['hold_recommended', 'verification_recommended']

export default function DecisionDrawer({
  decisions,
  unverified,
  onDecide,
  onClose,
}: {
  decisions: Case['decisions']
  unverified: boolean
  onDecide: (decision: DecisionValue, note: string, escalateTo?: EscalationTarget) => Promise<void>
  onClose: () => void
}) {
  const [decision, setDecision] = useState<DecisionValue>('requires_investigation')
  const [note, setNote] = useState('')
  const [target, setTarget] = useState<EscalationTarget>('fraud_specialist')
  const action = ACTIONS.find((a) => a.value === decision)!
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const close = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [onClose])

  async function save() {
    setError(null)
    try {
      await onDecide(decision, note, decision === 'escalated' ? target : undefined)
      setNote('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="fixed inset-0 z-40">
      <button type="button" aria-label="Close" className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <aside role="dialog" aria-label="Decision" className="absolute inset-y-0 right-0 flex w-full max-w-sm flex-col gap-4 overflow-y-auto bg-white p-4 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Decision</h2>
          <Button onClick={onClose}>Close</Button>
        </div>
        <div className="space-y-2">
          <select aria-label="Decision" className={`${inputClass} w-full`} value={decision} onChange={(e) => setDecision(e.target.value as DecisionValue)}>
            {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.text}</option>)}
          </select>
          {decision === 'escalated' && (
            <select aria-label="Escalate to" className={`${inputClass} w-full`} value={target} onChange={(e) => setTarget(e.target.value as EscalationTarget)}>
              <option value="fraud_specialist">To a fraud specialist</option>
              <option value="supervisor">To a supervisor</option>
            </select>
          )}
          <textarea aria-label="Note" className={`${inputClass} w-full`} rows={4} placeholder={action.hint ?? (unverified ? 'A note is required for an Unverified report' : 'Note')} value={note} onChange={(e) => setNote(e.target.value)} />
          {RECOMMENDATIONS.includes(decision) && (
            <p className="rounded-md bg-amber-100 p-2 text-xs text-amber-900">This is recorded as a recommendation only. Nothing happens to the customer's account or transactions.</p>
          )}
          <Button primary onClick={save}>Record Decision</Button>
          <ErrorNote message={error} />
          <p className="text-xs text-slate-500">Recording a Decision does not carry out any action. The original Alert never changes.</p>
        </div>
        {decisions.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-slate-500">History</h3>
            <ol className="mt-1 space-y-2 text-sm">
              {[...decisions].reverse().map((d) => (
                <li key={d.at + d.decision}>
                  <strong>{label(d.decision)}{d.escalate_to ? ` to ${label(d.escalate_to).toLowerCase()}` : ''}</strong>
                  <span className="text-xs text-slate-500"> {d.analyst}, {when(d.at)}</span>
                  {d.note && <p className="text-slate-700">{d.note}</p>}
                </li>
              ))}
            </ol>
          </div>
        )}
      </aside>
    </div>
  )
}
