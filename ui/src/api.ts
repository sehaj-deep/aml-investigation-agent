// Typed client for the case API. All calls go through /api (proxied to FastAPI).

export type CaseStatus =
  | 'queued'
  | 'running'
  | 'pending_review'
  | 'decision_recorded'
  | 'approved'
  | 'rejected'
  | 'failed'

export type Priority = 'high' | 'medium' | 'low' | 'sample'

export interface DetectionFactor {
  feature: string
  label: string
  value: number | null
  contribution: number
}

export interface Alert {
  alert_id: string
  seed_bank: number
  seed_account: string
  window_start: string
  window_end: string
  detection_score?: number | null
  detection_rank?: number | null
  priority?: Priority | null
  trigger_tx_ids?: number[]
  detection_factors?: DetectionFactor[]
}

// A row of the alert queue: the alert plus the work status of its case.
export type WorkStatus = CaseStatus | 'new'

export interface QueueAlert {
  alert_id: string
  seed_bank: number
  seed_account: string
  window_start: string
  window_end: string
  score: number | null
  rank: number | null
  priority: Priority | null
  n_triggers: number
  reasons: DetectionFactor[] | null
  case_id: string | null
  status: WorkStatus
  recommended_action: string | null
  pattern: string | null
}

export interface AlertSummary {
  total: number
  by_priority: Record<string, number>
  by_status: Record<string, number>
}

export interface Trigger {
  tx_id: number
  timestamp: string
  from_bank: number
  from_account: string
  to_bank: number
  to_account: string
  amount_paid: string
  currency_paid: string
  amount_received: string
  currency_received: string
  payment_format?: string
  from_label: string
  to_label: string
}

export interface CaseRow {
  case_id: string
  alert_id: string
  status: CaseStatus
  model: string | null
  prompt_version: string | null
  created_at: string
  updated_at: string
  seed_bank: string | null
  seed_account: string | null
  pattern: string | null
  recommended_action: string | null
  confidence: string | null
  faithful: boolean | null
  n_warnings: number
  n_evidence: number
  risk_score: number | null
  risk_band: 'high' | 'medium' | 'low' | null
}

export interface Evidence {
  tx_id: number
  from_bank: string
  from_account: string
  to_bank: string
  to_account: string
  amount_paid: string
  currency_paid: string
  timestamp: string
}

export interface Draft {
  case_id: string
  pattern_hypothesis: string
  summary: string
  evidence: Evidence[]
  recommended_action: 'escalate' | 'close' | 'needs_more_info'
  confidence: 'low' | 'medium' | 'high'
  limitations: string
}

export interface GraphNode {
  label: string
  bank_id: number
  account: string
  hop: number | 'trace'
  senders?: number | null
  receivers?: number | null
  jurisdiction?: string | null
}

export interface GraphEdge {
  src: string
  dst: string
  n_tx: number
  totals: { currency: string; n_tx: number; total: string }[]
  first: string
  last: string
  tx_ids: number[]
}

export interface CaseGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  loops: { tx_id: number; src: string; dst: string; ts: string }[][]
}

export interface Candidate {
  id: string
  kind: string
  score: number
  accounts: string[]
  tx_ids: number[]
  reason: string
}

export interface Verification {
  faithful: boolean
  grounded: boolean
  cited: number
  evidence_rows: number
  missing_tx_ids: number[]
  failures: { tx_id: number; exists: boolean; mismatches: Record<string, unknown> }[]
}

export interface Decision {
  action: 'approve' | 'reject' | 'request_more'
  reason: string
  reviewer: string
  decided_at: string
  applied_at: string | null
}

export interface CaseRisk {
  score: number
  band: 'high' | 'medium' | 'low'
  subject: { score: number; rules: string[] }
  top_counterparty: { label: string; score: number; rules: string[] } | null
  counterparties: Record<string, { score: number; rules: string[] }>
}

export interface CaseDetail {
  case_id: string
  alert_id: string
  alert: Alert
  status: CaseStatus
  draft: Draft | null
  warnings: string[]
  metrics: Record<string, number | string | boolean | null>
  verification: Verification | null
  case_graph: CaseGraph | null
  analysis: {
    hypothesis: { pattern_hypothesis: string; pattern_accounts: unknown[]; rationale: string } | null
    candidates: Candidate[]
    aliases: Record<string, [number, string]>
    risk?: CaseRisk | null
    triggers?: Trigger[]
  } | null
  error: string | null
  provider: string | null
  model: string | null
  prompt_version: string | null
  created_at: string
  updated_at: string
  decisions: Decision[]
}

export interface Stats {
  by_status: Record<string, number>
  by_recommended_action: Record<string, number>
  by_pattern: Record<string, number>
  decisions: Record<string, number>
  verification: { faithful: number; checked: number }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  alerts: (params: { priority?: string; status?: string; q?: string; limit: number; offset: number }) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') qs.set(k, String(v))
    })
    return request<{ total: number; items: QueueAlert[] }>(`/alerts?${qs}`)
  },
  alertSummary: () => request<AlertSummary>('/alerts/summary'),
  openAlert: (alertId: string) =>
    request<{ case_id: string; created: boolean }>(`/alerts/${alertId}/open`, { method: 'POST' }),
  cases: () => request<CaseRow[]>('/cases'),
  case: (id: string) => request<CaseDetail>(`/cases/${id}`),
  timeline: (id: string) =>
    request<{ chain_valid: boolean; lines: string[] }>(`/cases/${id}/timeline`),
  audit: (id: string) =>
    request<{
      chain_valid: boolean
      events: { seq: number; event_type: string; actor: string; created_at: string; payload: Record<string, unknown> }[]
    }>(`/cases/${id}/audit`),
  stats: () => request<Stats>('/stats'),
  decide: (id: string, action: Decision['action'], reason: string, reviewer: string) =>
    request<{ status: string }>(`/cases/${id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ action, reason, reviewer }),
    }),
}
