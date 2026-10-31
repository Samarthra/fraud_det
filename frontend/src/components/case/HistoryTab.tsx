import { useState } from 'react'
import type { CaseDetail } from '../../api'
import { Badge, Button, ErrorNote, inputClass, label, when } from '../../ui'

export default function HistoryTab({
  history,
  notes,
  onAddNote,
}: {
  history: NonNullable<CaseDetail['history']>
  notes: NonNullable<CaseDetail['notes']>
  onAddNote: (text: string) => Promise<void>
}) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function save() {
    setError(null)
    try {
      await onAddNote(text)
      setText('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5 text-sm">
      <section className="space-y-2">
        <h2 className="font-semibold">Investigation notes ({notes.length})</h2>
        <textarea aria-label="Investigation note" rows={3} className={`${inputClass} w-full`} placeholder="Add a note. Notes can't be edited or removed." value={text} onChange={(e) => setText(e.target.value)} />
        <Button primary disabled={!text.trim()} onClick={save}>Add note</Button>
        <ErrorNote message={error} />
      </section>
      <section>
        <h2 className="mb-2 font-semibold">Evidence history</h2>
        <ol className="divide-y divide-slate-100 rounded-md border border-slate-200">
          {[...history].reverse().map((h, i) => (
            <li key={`${h.at}-${h.event}-${i}`} className="px-3 py-2">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>{when(h.at)}</span>
                <Badge>{label(h.event)}</Badge>
                <span>{h.actor}</span>
              </div>
              <p>{h.summary}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
