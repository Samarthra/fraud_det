import { useEffect, useState } from 'react'
import type { Case, DecisionValue } from '../../api'
import { Button, ErrorNote, inputClass, label, when } from '../../ui'

const DECISIONS: DecisionValue[] = ['requires_investigation', 'false_positive', 'confirmed_fraud', 'escalated']

export default function DecisionDrawer({
  decisions,
  unverified,
  onDecide,
  onClose,
}: {
  decisions: Case['decisions']
  unverified: boolean
  onDecide: (decision: DecisionValue, note: string) => Promise<void>
  onClose: () => void
}) {
  const [decision, setDecision] = useState<DecisionValue>('requires_investigation')
  const [note, setNote] = useState('')
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
      await onDecide(decision, note)
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
            {DECISIONS.map((d) => <option key={d} value={d}>{label(d)}</option>)}
          </select>
          <textarea aria-label="Note" className={`${inputClass} w-full`} rows={4} placeholder={unverified ? 'A note is required for an Unverified report' : 'Note'} value={note} onChange={(e) => setNote(e.target.value)} />
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
                  <strong>{label(d.decision)}</strong>
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
