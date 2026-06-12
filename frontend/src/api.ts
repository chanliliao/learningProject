const BASE_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8001') + '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path} returned ${res.status}`)
  return res.json()
}

export const getHealth = () => get<{ status: string }>('/health')
export const getDbHealth = () => get<{ status: string }>('/health/db')
export const getQdrantHealth = () => get<{ status: string }>('/health/qdrant')
export const getLlmHealth = () => get<{ status: string; reply: string }>('/health/llm')

export type TargetSchema = { id: number; name: string; version: string }
export type FieldMapping = {
  id: number
  run_id: number
  source_path: string
  target_path: string
  transform: string | null
  confidence: number | null
  flags: string[]
  status: string
}
export type StageResult = { id: number; run_id: number; stage: string; status: string; payload: Record<string, unknown>; created_at: string }
export type AuditEvent = { id: number; run_id: number; actor: string; action: string; before: unknown; after: unknown; created_at: string }
export type PipelineRun = { id: number; status: string; source_filename: string; created_at: string }
export type RunDetail = {
  run: PipelineRun
  stage_results: StageResult[]
  mappings: FieldMapping[]
  audit: AuditEvent[]
}

export const listTargetSchemas = () => get<TargetSchema[]>('/schemas')
export const startRun = (file: File, targetSchemaId: number) => {
  const form = new FormData()
  form.append('file', file)
  form.append('target_schema_id', String(targetSchemaId))
  return fetch(`${BASE_URL}/runs`, { method: 'POST', body: form }).then(async res => {
    if (!res.ok) throw new Error(`/runs returned ${res.status}`)
    return res.json() as Promise<{ run_id: number; status: string }>
  })
}
export const getRun = (id: number) => get<RunDetail>(`/runs/${id}`)
export const editField = (runId: number, fieldId: number, patch_body: { target_path?: string; transform?: string }) =>
  patch<FieldMapping>(`/runs/${runId}/fields/${fieldId}`, patch_body)
export const approveStage = (runId: number, stage: string) =>
  post<{ run_id: number; status: string }>(`/runs/${runId}/stages/${stage}/approve`)
export const rejectStage = (runId: number, stage: string) =>
  post<{ run_id: number; status: string }>(`/runs/${runId}/stages/${stage}/reject`)

export type CalibrationRow = {
  confidence_bucket: string
  total: number
  correct: number
  precision: number
}
export type EvalReport = {
  total_records: number
  total_proposed: number
  total_expected: number
  tp: number
  fp: number
  fn: number
  precision: number
  recall: number
  calibration: CalibrationRow[]
  total_cost: number
}
export const getEvalReport = () => get<EvalReport>('/eval/latest')

export type EditIntent = {
  run_id: number
  field_id: number
  new_target_path: string
  new_transform: string | null
  reason: string
}

export type SupportResponse = {
  answer: string
  proposed_edits: EditIntent[]
}

export const askSupport = (runId: number, question: string) =>
  post<SupportResponse>(`/runs/${runId}/support`, { question })

export const applyProposedEdit = (runId: number, intent: EditIntent) =>
  post<{ run_id: number; status: string }>(`/runs/${runId}/support/apply`, intent)
