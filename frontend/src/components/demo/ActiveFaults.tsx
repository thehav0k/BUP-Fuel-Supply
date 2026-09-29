import { ShieldCheck } from 'lucide-react'
import { useFaultsQuery } from '@/api/queries'
import type { FaultListResponse, FaultRecord } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useNow } from '@/lib/clock'
import { fmtSeconds, humanize } from '@/lib/format'

function toList(res: FaultListResponse | undefined): FaultRecord[] {
  if (!res) return []
  if (Array.isArray(res)) return res
  return res.items ?? res.faults ?? []
}

const str = (v: unknown) => (typeof v === 'string' ? v : null)
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** Seconds until the fault expires, if the record tells us. */
function remaining(f: FaultRecord, now: number): number | null {
  const r = num(f.remaining_seconds)
  if (r !== null) return r
  const exp = str(f.expires_at) ?? str(f.ends_at) ?? str(f.until)
  if (exp) {
    const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(exp) ? exp : `${exp}Z`)
    if (!Number.isNaN(t)) return (t - now) / 1000
  }
  const created = str(f.created_at) ?? str(f.started_at)
  const dur = num(f.duration_seconds)
  if (created && dur !== null) {
    const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(created) ? created : `${created}Z`)
    if (!Number.isNaN(t)) return (t + dur * 1000 - now) / 1000
  }
  return null
}

function isActive(f: FaultRecord, now: number): boolean | null {
  if (typeof f.active === 'boolean') return f.active
  if (typeof f.status === 'string') return f.status.toUpperCase() === 'ACTIVE'
  const r = remaining(f, now)
  return r === null ? null : r > 0
}

function paramText(p: unknown): string {
  if (!p || typeof p !== 'object') return ''
  const entries = Object.entries(p as Record<string, unknown>)
  return entries.map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : String(v)}`).join(', ')
}

export function ActiveFaults() {
  const { data, isError } = useFaultsQuery()
  const now = useNow()
  const all = toList(data)
  const rows = all.map((f, i) => ({ f, i, active: isActive(f, now), left: remaining(f, now) }))
  const active = rows.filter((r) => r.active !== false)
  const expired = rows.filter((r) => r.active === false).slice(0, 5)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Active faults</CardTitle>
          <Badge tone={active.length ? 'crit' : 'ok'}>{active.length}</Badge>
        </div>
        <CardDescription>From GET /api/demo/faults (the simulator keeps the last 50).</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5">
        {isError && !data ? (
          <div className="text-xs text-crit-ink">Could not load faults (demo controls may be disabled).</div>
        ) : active.length === 0 ? (
          <div className="flex items-center gap-1.5 py-2 text-xs text-muted-foreground">
            <ShieldCheck className="size-4 text-ok-ink" aria-hidden /> No active faults.
          </div>
        ) : (
          active.map(({ f, i, left, active: a }) => (
            <div key={String(f.id ?? i)} className="flex items-center gap-2 rounded-md bg-crit/8 px-2 py-1.5 text-xs ring-1 ring-crit/25 ring-inset">
              <span className="font-semibold text-crit-ink">{humanize(str(f.type) ?? 'fault')}</span>
              <span className="text-muted-foreground">{paramText(f.parameters)}</span>
              <span className="tnum ml-auto text-muted-foreground">
                {left !== null && left > 0 ? `${fmtSeconds(left)} left` : a === null ? 'status unknown' : 'active'}
              </span>
            </div>
          ))
        )}
        {expired.length > 0 ? (
          <div className="mt-1 border-t pt-1.5">
            <div className="mb-1 text-[11px] font-medium text-muted-foreground">Recently expired</div>
            {expired.map(({ f, i }) => (
              <div key={String(f.id ?? `x${i}`)} className="flex gap-2 py-0.5 text-[11px] text-muted-foreground">
                <span>{humanize(str(f.type) ?? 'fault')}</span>
                <span>{paramText(f.parameters)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
