import { useStateQuery } from './queries'
import { ApiError } from './client'
import { useNow } from '@/lib/clock'

export interface Connection {
  /** The latest poll of /api/state failed (backend down, proxy error, timeout). */
  backendDown: boolean
  errorCode: string | null
  errorMessage: string | null
  /** Seconds since the browser last received a good /api/state response. */
  sinceLastResponseS: number | null
  /**
   * Age of the simulator data on screen, in seconds: the backend's own
   * data_age_s at response time plus the time since we received it. This keeps
   * growing if the backend becomes unreachable, and is immune to clock skew.
   */
  dataAgeS: number | null
}

export function useConnection(): Connection {
  const q = useStateQuery()
  const now = useNow()
  const received = q.dataUpdatedAt > 0 ? Math.max(0, (now - q.dataUpdatedAt) / 1000) : null
  const backendAge = q.data?.data_age_s ?? null
  const err = q.isError ? q.error : null
  return {
    backendDown: q.isError,
    errorCode: err instanceof ApiError ? err.code : err ? 'ERROR' : null,
    errorMessage: err ? err.message : null,
    sinceLastResponseS: received,
    dataAgeS: backendAge !== null && received !== null ? backendAge + received : null,
  }
}
