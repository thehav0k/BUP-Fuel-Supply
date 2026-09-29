import { errorInfo } from '@/api/client'
import type { Recommendation, RecommendationActionResult } from '@/api/types'

/** What happened when the operator approved/rejected a recommendation, kept after the card leaves the open list. */
export interface ActionOutcome {
  id: string
  action: 'approve' | 'reject'
  ok: boolean
  code: string | null
  message: string | null
  note?: string
  rec: Recommendation | null
}

export function outcomeFromResult(
  id: string,
  action: 'approve' | 'reject',
  res: RecommendationActionResult,
  note?: string,
): ActionOutcome {
  return {
    id,
    action,
    ok: res.ok,
    code: res.error?.code ?? null,
    message: res.error?.message ?? null,
    note,
    rec: res.recommendation ?? null,
  }
}

export function outcomeFromError(id: string, action: 'approve' | 'reject', err: unknown, rec: Recommendation | null): ActionOutcome {
  const { code, message } = errorInfo(err)
  return { id, action, ok: false, code, message, rec }
}
