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
}

export type EvalStatus = {
  running: boolean
  done: number
  total: number
  current: string | null
  last_error: string | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const KEY = 'fraudlens-analyst'

export function currentAnalyst(): string {
  try {
    return localStorage.getItem(KEY) ?? 'analyst-1'
  } catch {
    return 'analyst-1'
  }
}

export function chooseAnalyst(id: string) {
  try {
    localStorage.setItem(KEY, id)
  } catch {
    // The picker still works for this page load.
  }
  analyst = id
}

let analyst = currentAnalyst()

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { 'X-Analyst-Id': analyst }
  try {
    headers['Authorization'] = `Basic ${btoa(`${analyst}:password`)}`
  } catch {
    // ignore
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
  stats: () => request<Stats>('/stats'),
  alerts: (filters: Record<string, string>) => {
    const set = Object.entries(filters).filter(([, value]) => value)
    return request<Alert[]>(`/alerts?${new URLSearchParams(set)}`)
  },
  cases: () => request<Case[]>('/cases'),
  caseDetail: (id: string) => request<CaseDetail>(`/cases/${id}`),
  decide: (id: string, decision: DecisionValue, note: string) =>
    post<Case>(`/cases/${id}/decision`, { decision, note }),
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
