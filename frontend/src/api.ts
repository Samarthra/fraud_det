import type { components } from './api-types'

type S = components['schemas']
export type Analyst = S['Analyst']
export type Alert = S['Alert']
export type Case = S['Case']
export type CaseDetail = S['CaseDetail']
export type Investigation = S['Investigation']
export type Report = S['Report']
export type Step = S['Step']
export type Evidence = S['Evidence']
export type FollowUp = S['FollowUp']
export type Stats = S['Stats']
export type UploadResult = S['UploadResult']
export type DecisionValue = S['DecisionRequest']['decision']
export type EscalationTarget = NonNullable<S['DecisionRequest']['escalate_to']>
export type RiskLevel = S['ClassificationRequest']['risk_level']
export type CaseGraph = S['CaseGraph']
export type Priority = S['Priority']

export type AuditRow = {
  seq: number
  event: string
  at: string
  details: Record<string, unknown>
  trace_url: string | null
}

export type EvalCase = {
  case_id: string
  group: string
  expected: string
  assessment: string | null
  verification: string | null
  failures: string[]
  seconds: number
  trace_url: string | null
}

export type EvalRun = {
  run_at: string
  commit: string
  model: string
  estimated_cost_inr: number
  notice: string
  detection: {
    precision: number
    recall: number
    true_positives: number
    false_positives: number
    false_negatives: number
    true_negatives: number
    misses_by_story: Record<string, number>
  } | null
  scenarios: { name: string; correct: number; runs: number; gate: number; passed: boolean }[]
  injection_passed: number
  injection_total: number
  denials_passed: number
  denials_total: number
  held_out_correct: number
  held_out_total: number
  failures: EvalCase[]
  typology?: {
    sweep: { stories: Record<string, { fraud?: boolean; alerts: number; suspicious: number; not_suspicious: number; none: number }>; wrong: { subject: string; story: string; requirement: string }[] }
    retries: number
    unverified_by_mismatch: number
    model_calls: number
    calls_per_investigation: number
    seconds_per_investigation: number
    reader: { phrase_match: { correct: number; total: number }; llm: { correct: number; total: number }; llm_stays: boolean } | null
    baseline: Record<string, number | string> | null
    keep: boolean | null
    keep_reasons: string[]
  } | null
}

export type EvalStatus = {
  running: boolean
  done: number
  total: number
  current: string | null
  last_error: string | null
}

export type Graph = {
  nodes: { id: string; type: string; label: string }[]
  edges: { source: string; target: string; label: string }[]
  more_in_portfolio: number
  out_of_scope_count: number
}

export type GraphNodeDetail = {
  id: string
  type: string
  title: string
  facts: { label: string; value: string }[]
  accounts: string[]
  out_of_scope_count: number
  cases: { id: string; category: string; risk_level: string }[]
  records?: { kind: string; source_ref: string; data: Record<string, unknown> }[]
}

export type DetectionRules = {
  thresholds: { record: number; actionable: number; high: number }
  rules: Record<string, Record<string, number | string>>
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const KEY = 'fraudlens-analyst'
const PWD = 'fraudlens-password'

export function currentAnalyst(): string {
  try {
    return localStorage.getItem(KEY) ?? 'analyst-1'
  } catch {
    return 'analyst-1'
  }
}

export function currentPassword(): string | null {
  try {
    return localStorage.getItem(PWD)
  } catch {
    return null
  }
}

export function chooseAnalyst(id: string, password?: string | null) {
  try {
    localStorage.setItem(KEY, id)
    if (password) localStorage.setItem(PWD, password)
  } catch {
    // The picker still works for this page load.
  }
  analyst = id
  if (password) passwordState = password
}

export function clearSession() {
  try {
    localStorage.removeItem(KEY)
    localStorage.removeItem(PWD)
  } catch {
    // ignore
  }
  passwordState = null
}

let analyst = currentAnalyst()
let passwordState: string | null = currentPassword()

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const pwd = passwordState ?? currentPassword()
  if (pwd) {
    try {
      headers['Authorization'] = `Basic ${btoa(`${analyst}:${pwd}`)}`
    } catch {
      // ignore
    }
  }
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json'
  const response = await fetch(`/api${path}`, { ...init, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.detail ?? response.statusText)
  }
  return response.json()
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  analysts: () => request<Analyst[]>('/analysts'),
  me: () => request<Analyst>('/me'),
  login: async (username: string, password: string) => {
    const token = btoa(`${username}:${password}`)
    const response = await fetch('/api/me', { headers: { Authorization: `Basic ${token}` } })
    if (!response.ok) throw new ApiError(response.status, 'Invalid credentials')
    const a = await response.json() as Analyst
    chooseAnalyst(a.id, password)
    analyst = a.id
    passwordState = password
    return a
  },
  stats: () => request<Stats>('/stats'),
  graph: (accountId: string) => request<Graph>(`/graph?account_id=${encodeURIComponent(accountId)}`),
  graphNode: (id: string, type: string) =>
    request<GraphNodeDetail>(`/graph/node?${new URLSearchParams({ id, type })}`),
  detectionRules: () => request<DetectionRules>('/detection/rules'),
  alerts: (filters: Record<string, string>) => {
    const set = Object.entries(filters).filter(([, value]) => value)
    return request<Alert[]>(`/alerts?${new URLSearchParams(set)}`)
  },
  cases: () => request<Case[]>('/cases'),
  caseDetail: (id: string) => request<CaseDetail>(`/cases/${id}`),
  decide: (id: string, decision: DecisionValue, note: string, escalateTo?: EscalationTarget) =>
    post<Case>(`/cases/${id}/decision`, { decision, note, escalate_to: escalateTo ?? null }),
  addNote: (id: string, text: string) => post<unknown>(`/cases/${id}/notes`, { text }),
  reclassify: (id: string, riskLevel: RiskLevel, reason: string) =>
    post<Case>(`/cases/${id}/risk`, { risk_level: riskLevel, reason }),
  separate: (id: string, alertId: string, reason: string) =>
    post<Case>(`/cases/${id}/alerts/${alertId}/separate`, { reason }),
  downloadReport: async (id: string) => {
    const report = await request<unknown>(`/cases/${id}/report`)
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${id}_report.json`
    link.click()
    URL.revokeObjectURL(url)
  },
  investigate: (id: string, replay: boolean) =>
    post<{ investigation_id: string }>(`/cases/${id}/investigation`, { replay }),
  investigation: (id: string) => request<Investigation>(`/investigations/${id}`),
  steps: (id: string, after: number) => request<Step[]>(`/investigations/${id}/steps?after=${after}`),
  followUp: (id: string, question: string) => post<FollowUp>(`/investigations/${id}/followups`, { question }),
  upload: (dataset: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<UploadResult>(`/ingest/${dataset}`, { method: 'POST', body })
  },
  loadSample: () => post<{ alerts_created: number; already_loaded: boolean }>('/demo/sample'),
  reset: () => post<{ alerts_created: number }>('/demo/reset'),
  rerun: () => post<{ alerts_created: number }>('/detection/rerun'),
  evals: () => request<EvalRun>('/evals/latest'),
  evalStatus: () => request<EvalStatus>('/evals/status'),
  runEvals: () => post<{ started: boolean }>('/evals/run'),
  audit: () => request<AuditRow[]>('/audit'),
}
