import { useEffect, useState } from 'react'
import { api, type DetectionRules as Rules } from '../api'
import { Badge, Card, ErrorNote, Risk } from '../ui'

type Rule = Record<string, number | string>

const TRIGGERS: Record<string, (r: Rule) => string> = {
  new_device: (r) => `Device first seen on this account under ${r.hours}h ago`,
  amount_spike: (r) => `Amount over ${r.multiplier}× the account's ${r.window_days}-day median, with at least ${r.min_history} earlier payments, unless similar large payments are already regular`,
  new_beneficiary: () => 'First payment from this account to this beneficiary',
  mule_beneficiary: (r) => `${r.accounts}+ accounts paid this beneficiary in ${r.window_days} days`,
  velocity: (r) => `${r.payments}+ outgoing payments in ${r.minutes} minutes`,
  foreign_ip: (r) => `IP country differs from ${r.home_country}`,
  off_hours: (r) => `Between ${String(r.start_hour).padStart(2, '0')}:00 and ${String(r.end_hour).padStart(2, '0')}:00 IST`,
  shared_device: (r) => `${r.customers}+ customers on one device in ${r.window_days} days. Scores ${r.family_points} if they all share a surname and address`,
  login_failures_then_success: (r) => `${r.failures}+ failed logins, then a success within ${r.within_minutes} minutes. Also applies to a payment within ${r.transfer_within_minutes} minutes after`,
  multi_applicant_device: (r) => `${r.customers}+ customers apply for loans from one device in ${r.window_days} days`,
}

const NAMES: Record<string, string> = {
  new_device: 'New device',
  amount_spike: 'Amount spike',
  new_beneficiary: 'New beneficiary',
  mule_beneficiary: 'Mule beneficiary',
  velocity: 'Rapid payments',
  foreign_ip: 'Foreign IP',
  off_hours: 'Unusual hours',
  shared_device: 'Shared device',
  login_failures_then_success: 'Failed logins, then success',
  multi_applicant_device: 'Multiple loan applicants',
}

const EXAMPLE = ['new_device', 'amount_spike', 'new_beneficiary', 'mule_beneficiary', 'foreign_ip', 'login_failures_then_success']

export default function DetectionRules() {
  const [rules, setRules] = useState<Rules | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.detectionRules().then(setRules).catch((e) => setError(e.message))
  }, [])

  if (!rules) return <ErrorNote message={error} />
  const { thresholds, rules: all } = rules
  const example = EXAMPLE.filter((name) => all[name])
  const total = example.reduce((sum, name) => sum + Number(all[name].points), 0)
  const score = Math.min(100, total)
  const band = score >= thresholds.high ? 'high' : score >= thresholds.actionable ? 'medium' : 'low'

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Detection rules</h1>
        <p className="mt-1 text-sm text-slate-600">How FraudLens decides what to flag. These values are read live from the rules file, so this page always matches what detection uses.</p>
      </div>

      <Card title="How scoring works">
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>Every transaction, login pattern, shared device and loan application is checked against the rules below.</li>
          <li>Each rule that matches adds its points and records a reason, and the total is capped at 100.</li>
          <li>Rules in code decide what gets flagged. The AI agent only starts when an Analyst opens a Case and presses Investigate, and a human makes the Decision.</li>
        </ol>
      </Card>

      <Card title="Rules">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-slate-500"><tr><th className="py-1 pr-4">Rule</th><th className="pr-4">Fires when</th><th className="text-right">Points</th></tr></thead>
            <tbody>
              {Object.entries(all).map(([name, rule]) => (
                <tr key={name} className="border-t border-slate-100 align-top">
                  <td className="whitespace-nowrap py-1.5 pr-4 font-medium">{NAMES[name] ?? name}</td>
                  <td className="py-1.5 pr-4">{TRIGGERS[name]?.(rule) ?? 'Custom rule'}</td>
                  <td className="py-1.5 text-right tabular-nums">{rule.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="What the score means">
          <table className="w-full text-sm">
            <tbody>
              <tr><td className="py-1 pr-3 text-slate-500">Under {thresholds.record}</td><td className="py-1">Not recorded</td></tr>
              <tr className="border-t border-slate-100"><td className="py-1 pr-3"><Risk level="low" /> {thresholds.record}-{thresholds.actionable - 1}</td><td>Alert recorded, no Case</td></tr>
              <tr className="border-t border-slate-100"><td className="py-1 pr-3"><Risk level="medium" /> {thresholds.actionable}-{thresholds.high - 1}</td><td>Alert, and a Case opens</td></tr>
              <tr className="border-t border-slate-100"><td className="py-1 pr-3"><Risk level="high" /> {thresholds.high}-100</td><td>Alert, and a Case opens</td></tr>
            </tbody>
          </table>
        </Card>
        <Card title="Worked example: TXN-50001 in the sample data">
          <ul className="space-y-1 text-sm">
            {example.map((name) => (
              <li key={name} className="flex justify-between gap-4"><span>{NAMES[name]}</span><span className="tabular-nums text-slate-500">+{all[name].points}</span></li>
            ))}
            <li className="flex items-center justify-between gap-4 border-t border-slate-200 pt-1 font-medium">
              <span>Total {total}{total > 100 ? ', capped at 100' : ''}</span>
              <span className="flex items-center gap-2">{score} <Risk level={band} /></span>
            </li>
          </ul>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Avoiding false alarms">
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>A large payment alone can't open a Case, because the amount rule's points fall short of {thresholds.actionable}.</li>
            <li>A customer who regularly sends similar amounts doesn't trigger the amount rule.</li>
            <li>A family sharing a phone scores low, while unrelated customers on one device score high.</li>
          </ul>
        </Card>
        <Card title="What these rules miss" action={<Badge tone="amber">Known limits</Badge>}>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            <li>Slow bleed: small amounts to a known payee look like normal activity.</li>
            <li>Mule payments made before a beneficiary reaches the account threshold.</li>
            <li>Anything without a matching rule. See Evaluations for measured misses.</li>
          </ul>
        </Card>
      </div>

      <p className="text-xs text-slate-500">To change a rule, edit <code>backend/app/detection/rules.yaml</code>, then press Re-run detection on the Dashboard. A re-run only adds Alerts, and existing Alerts and Cases never change.</p>
    </div>
  )
}
