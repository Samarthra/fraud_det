// PROTOTYPE, throwaway. Three ways to show a Typology proof on the existing Case page, via ?variant=.
// Proof content is a read-only stub copied from the prototype's output on real seeded records.
import { useEffect, useState } from 'react'
import { Badge, Button } from '../../ui'

type Line = { text: string; ref: string }
type Proof = { name: string; account: string; kind: 'fraud' | 'legit'; lines: Line[] }
type Sample = { label: string; requires: string; proofs: Proof[]; near: string[]; draft?: string; error?: string }

const TAKEOVER: Proof = { name: 'Account takeover', account: 'ACC-10042', kind: 'fraud', lines: [
  { text: 'SIM swap on the account', ref: 'EVT-45' },
  { text: 'Password reset', ref: 'EVT-46' },
  { text: '4 failed logins, then a success', ref: 'LOG-13599' },
  { text: 'DEV-9001 is new to this account', ref: 'TXN-50001' },
  { text: 'TXN-50001 pays first-time beneficiary BEN-7001, ₹1,85,000', ref: 'TXN-50001' },
] }
const MULE: Proof = { name: 'Mule payment', account: 'ACC-10042', kind: 'fraud', lines: [
  { text: 'TXN-50001 is the first payment to BEN-7001', ref: 'TXN-50001' },
  { text: '7 accounts paid BEN-7001 within 7 days, some outside your Portfolio', ref: 'TXN-50001' },
] }
const DEVICE: Proof = { name: 'Verified device change', account: 'ACC-20017', kind: 'legit', lines: [
  { text: 'DEV-9002 enrolled', ref: 'EVT-48' },
  { text: 'Text says "passed OTP" (quoted from the record)', ref: 'EVT-48' },
  { text: 'No failed login, SIM swap or password reset in the 24 hours before', ref: 'EVT-48' },
] }
const PAYEE: Proof = { name: 'Established payee', account: 'ACC-20017', kind: 'legit', lines: [
  { text: 'BEN-7002 added 47 hours before its first payment', ref: 'EVT-49' },
  { text: 'Only this account has ever paid BEN-7002', ref: 'TXN-50002' },
] }
const SAMPLES: Record<string, Sample> = {
  takeover: { label: 'Fraud proved', requires: 'Suspicious', proofs: [TAKEOVER, MULE], near: [] },
  clear: { label: 'Fully explained', requires: 'Not suspicious', proofs: [DEVICE, PAYEE], near: [] },
  mismatch: { label: 'Agent disagreed', requires: 'Suspicious', proofs: [TAKEOVER], near: [], draft: 'Not suspicious', error: 'Account takeover is proved on ACC-10042, but the draft says not suspicious after one retry. This report is Unverified, so your Decision needs a note.' },
  none: { label: 'Nothing proved', requires: 'No requirement', proofs: [], near: ['Account takeover: a compromise signal within 2 hours', 'Verified device change: blocked by LOG-13001'] },
}
const ALL = [['Account takeover', 'fraud'], ['Mule payment', 'fraud'], ['Loan proceeds diversion', 'fraud'], ['Staged claim ring', 'fraud'], ['Verified device change', 'legit'], ['Established payee', 'legit']] as const
const VARIANTS = [['A', 'Always-on strip'], ['B', 'Proof trail in the report'], ['C', 'Typology scoreboard']] as const

const param = (name: string, fallback: string) => new URLSearchParams(window.location.search).get(name) ?? fallback
export const proofVariant = () => param('variant', 'A')
const sample = () => SAMPLES[param('proof', 'takeover')] ?? SAMPLES.takeover
const tone = (s: Sample) => s.requires === 'Suspicious' ? 'red' : s.requires === 'Not suspicious' ? 'green' : 'slate'

function Trail({ proof }: { proof: Proof }) {
  return (
    <ol className="space-y-1.5 border-l-2 pl-3" style={{ borderColor: proof.kind === 'fraud' ? '#dc2626' : '#059669' }}>
      {proof.lines.map((l) => (
        <li key={l.text} className="flex items-baseline justify-between gap-3 text-sm">
          <span>✓ {l.text}</span>
          <span className="shrink-0 rounded bg-blue-50 px-1.5 py-0.5 text-xs font-medium text-blue-800">{l.ref}</span>
        </li>
      ))}
    </ol>
  )
}

/** A: one line under the header on every tab, which opens the full proof. */
export function VariantStrip() {
  const s = sample()
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">Typology check</span>
        <Badge tone={tone(s)}>Requires: {s.requires}</Badge>
        {s.proofs.map((p) => <Badge key={p.name} tone={p.kind === 'fraud' ? 'red' : 'green'}>{p.name}</Badge>)}
        {s.draft && <Badge tone="amber">Agent said: {s.draft}</Badge>}
        {s.near.length > 0 && <span className="text-slate-500">{s.near.length} nearly proved</span>}
        <span className="ml-auto"><Button onClick={() => setOpen((v) => !v)}>{open ? 'Hide proof' : 'Show proof'}</Button></span>
      </div>
      {open && (
        <div className="mt-2 space-y-3 border-t border-slate-100 pt-2">
          {s.error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-800">{s.error}</p>}
          {s.proofs.map((p) => <div key={p.name}><p className="mb-1 text-sm font-medium">{p.name} on {p.account}</p><Trail proof={p} /></div>)}
          {s.near.map((n) => <p key={n} className="text-sm text-slate-600">Missing: {n}</p>)}
        </div>
      )}
    </div>
  )
}

/** B: the proof reads first inside the AI report, ahead of the agent's own words. */
export function VariantTrail() {
  const s = sample()
  return (
    <div className="mx-auto mb-4 max-w-3xl space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">What code proved, before the AI wrote anything</h3>
        <Badge tone={tone(s)}>Requires: {s.requires}</Badge>
      </div>
      {s.error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-800">{s.error}</p>}
      {s.proofs.map((p) => (
        <div key={p.name} className="rounded-md border border-slate-200 p-3">
          <p className="mb-2 text-sm font-medium">{p.name} <span className="font-normal text-slate-500">on {p.account}</span></p>
          <Trail proof={p} />
        </div>
      ))}
      {s.proofs.length === 0 && <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">No Typology was proved, so the agent's Assessment stands on its own.</p>}
      {s.near.length > 0 && <ul className="list-disc pl-5 text-sm text-slate-600">{s.near.map((n) => <li key={n}>Nearly proved. {n}</li>)}</ul>}
    </div>
  )
}

/** C: its own tab, every Typology on one board, so an absence is as visible as a proof. */
export function VariantBoard() {
  const s = sample()
  const proved = new Map(s.proofs.map((p) => [p.name, p]))
  const near = (name: string) => s.near.find((n) => n.startsWith(name))
  const [picked, setPicked] = useState(s.proofs[0]?.name ?? ALL[0][0])
  const proof = proved.get(picked)
  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-3 flex items-center gap-2"><h2 className="font-semibold">Typology check</h2><Badge tone={tone(s)}>Requires: {s.requires}</Badge>{s.draft && <Badge tone="amber">Agent said: {s.draft}</Badge>}</div>
      {s.error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-800">{s.error}</p>}
      <div className="grid gap-4 md:grid-cols-[17rem_1fr]">
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 text-sm">
          {ALL.map(([name, kind]) => (
            <li key={name}>
              <button type="button" onClick={() => setPicked(name)} className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left ${picked === name ? 'bg-slate-100' : ''}`}>
                <span>{name}</span>
                {proved.has(name) ? <Badge tone={kind === 'fraud' ? 'red' : 'green'}>Proved</Badge> : near(name) ? <Badge tone="amber">Nearly</Badge> : <span className="text-xs text-slate-400">Not proved</span>}
              </button>
            </li>
          ))}
        </ul>
        <div className="text-sm">
          <p className="mb-2 font-medium">{picked}</p>
          {proof ? <Trail proof={proof} /> : <p className="text-slate-600">{near(picked) ? `Missing: ${near(picked)!.split(': ')[1]}` : 'The records show nothing that fits this Typology.'}</p>}
        </div>
      </div>
    </div>
  )
}

export function ProofPrototypeBar() {
  const key = proofVariant()
  const go = (next: Record<string, string>) => {
    const url = new URL(window.location.href)
    Object.entries(next).forEach(([k, v]) => url.searchParams.set(k, v))
    window.location.replace(url.toString())
  }
  const step = (by: number) => {
    const i = VARIANTS.findIndex(([k]) => k === key)
    go({ variant: VARIANTS[(i + by + VARIANTS.length) % VARIANTS.length][0] })
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable) return
      if (e.key === 'ArrowLeft') step(-1)
      if (e.key === 'ArrowRight') step(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  if (!import.meta.env.DEV) return null
  return (
    <div className="fixed bottom-4 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm text-white shadow-lg">
      <button type="button" aria-label="Previous variant" onClick={() => step(-1)}>←</button>
      <span>{key} ({VARIANTS.find(([k]) => k === key)?.[1]})</span>
      <button type="button" aria-label="Next variant" onClick={() => step(1)}>→</button>
      <select aria-label="Sample" className="rounded bg-slate-700 px-1 py-0.5" value={param('proof', 'takeover')} onChange={(e) => go({ proof: e.target.value })}>
        {Object.entries(SAMPLES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
      </select>
    </div>
  )
}
