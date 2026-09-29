import type {
  AllocationList,
  CancelAllocationResult,
  CreateEventBody,
  CreateFaultBody,
  DecisionList,
  EventList,
  FaultListResponse,
  Forecast,
  Health,
  Mode,
  RecommendationActionResult,
  RecommendationList,
  Settings,
  State,
  StepResult,
} from './types'

/** Same origin: /api/... and /health are proxied (Vite in dev, nginx in Docker). */
const BASE = ''
const TIMEOUT_MS = 10_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly body: unknown

  constructor(status: number, code: string, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.body = body
  }

  /** True when the backend itself could not be reached (network error or proxy 5xx). */
  get unreachable(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504
  }
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/** Accepts {detail:{code,message}}, {detail:[...]} (pydantic 422), {error:{code,message}} and plain strings. */
function parseErrorBody(status: number, body: unknown, fallbackText: string): { code: string; message: string } {
  if (isRecord(body)) {
    const detail = body.detail ?? body.error
    if (isRecord(detail)) {
      const code = typeof detail.code === 'string' ? detail.code : `HTTP_${status}`
      const message = typeof detail.message === 'string' ? detail.message : code
      return { code, message }
    }
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (isRecord(d) && typeof d.msg === 'string' ? d.msg : JSON.stringify(d)))
        .join('; ')
      return { code: 'VALIDATION_ERROR', message: msgs || 'Validation error' }
    }
    if (typeof detail === 'string') return { code: `HTTP_${status}`, message: detail }
  }
  const text = fallbackText.trim()
  return {
    code: status >= 500 ? 'BACKEND_ERROR' : `HTTP_${status}`,
    message: text && text.length < 300 && !text.startsWith('<') ? text : `Request failed with HTTP ${status}`,
  }
}

function withTimeout(signal?: AbortSignal): AbortSignal {
  const timeout = AbortSignal.timeout(TIMEOUT_MS)
  return signal ? AbortSignal.any([signal, timeout]) : timeout
}

async function request<T>(
  path: string,
  opts: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const { method = 'GET', body, signal } = opts
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: withTimeout(signal),
      cache: 'no-store',
    })
  } catch (err) {
    if (signal?.aborted) throw err // cancelled by TanStack Query, not a failure
    const timedOut = err instanceof DOMException && err.name === 'TimeoutError'
    throw new ApiError(0, timedOut ? 'TIMEOUT' : 'NETWORK_ERROR', timedOut ? 'Backend timed out' : 'Backend unreachable')
  }

  const text = await res.text()
  let parsed: unknown = undefined
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = undefined
    }
  }

  if (!res.ok) {
    const { code, message } = parseErrorBody(res.status, parsed, text)
    throw new ApiError(res.status, code, message, parsed)
  }
  if (parsed === undefined && text) {
    // 200 with a non-JSON body usually means the SPA fallback answered instead of the backend.
    throw new ApiError(502, 'BAD_RESPONSE', 'Backend returned a non-JSON response')
  }
  return parsed as T
}

const post = <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body })

export const api = {
  health: (signal?: AbortSignal) => request<Health>('/health', { signal }),
  state: (signal?: AbortSignal) => request<State>('/api/state', { signal }),
  forecast: (stationId: string, signal?: AbortSignal) =>
    request<Forecast>(`/api/forecast?station_id=${encodeURIComponent(stationId)}`, { signal }),

  recommendations: (status: 'open' | 'all', signal?: AbortSignal) =>
    request<RecommendationList>(`/api/recommendations?status=${status}`, { signal }),
  approve: (id: string) => post<RecommendationActionResult>(`/api/recommendations/${encodeURIComponent(id)}/approve`),
  reject: (id: string, note?: string) =>
    post<RecommendationActionResult>(`/api/recommendations/${encodeURIComponent(id)}/reject`, note ? { note } : {}),

  allocations: (limit = 50, signal?: AbortSignal) =>
    request<AllocationList>(`/api/allocations?limit=${limit}`, { signal }),
  cancelAllocation: (id: number) => post<CancelAllocationResult>(`/api/allocations/${id}/cancel`),

  decisions: (limit = 100, signal?: AbortSignal) =>
    request<DecisionList>(`/api/decisions?limit=${limit}`, { signal }),
  events: (signal?: AbortSignal) => request<EventList>('/api/events', { signal }),

  settings: (signal?: AbortSignal) => request<Settings>('/api/settings', { signal }),
  setMode: (mode: Mode) => request<Settings>('/api/settings', { method: 'PUT', body: { mode } }),

  demo: {
    run: () => post<unknown>('/api/demo/run'),
    pause: () => post<unknown>('/api/demo/pause'),
    step: (count: number) => post<StepResult>('/api/demo/step', { count }),
    reset: () => post<unknown>('/api/demo/reset'),
    createEvent: (body: CreateEventBody) => post<unknown>('/api/demo/events', body),
    faults: (signal?: AbortSignal) => request<FaultListResponse>('/api/demo/faults', { signal }),
    createFault: (body: CreateFaultBody) => post<unknown>('/api/demo/faults', body),
    clearFaults: () => post<unknown>('/api/demo/faults/clear'),
  },
}

export function errorInfo(err: unknown): { code: string; message: string } {
  if (err instanceof ApiError) return { code: err.code, message: err.message }
  if (err instanceof Error) return { code: 'ERROR', message: err.message }
  return { code: 'ERROR', message: String(err) }
}
