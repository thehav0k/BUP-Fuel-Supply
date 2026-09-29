import { CloudOff, Database, FlaskConical, OctagonAlert, TriangleAlert, Unplug } from 'lucide-react'
import type { ReactNode } from 'react'
import { useConnection } from '@/api/connection'
import { useStateQuery } from '@/api/queries'
import type { LucideIcon } from 'lucide-react'
import { fmtAgo, fmtSeconds } from '@/lib/format'
import { cn } from '@/lib/utils'

type BannerTone = 'crit' | 'warn' | 'info'

const TONE: Record<BannerTone, string> = {
  crit: 'bg-crit/12 text-crit-ink border-crit/30',
  warn: 'bg-warn/15 text-warn-ink border-warn/40',
  info: 'bg-series-1/10 text-info-ink border-series-1/30',
}

function Banner({ tone, icon: Icon, title, children }: { tone: BannerTone; icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div role={tone === 'crit' ? 'alert' : 'status'} className={cn('flex items-start gap-2 border-t px-4 py-1.5 text-[13px]', TONE[tone])}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">
        <span className="font-semibold">{title}</span>
        {children ? <span className="text-foreground/80"> — {children}</span> : null}
      </div>
    </div>
  )
}

/** Global banners. Always rendered under the top bar whenever the condition is active. */
export function Banners() {
  const { data: s } = useStateQuery()
  const conn = useConnection()
  const critical = (s?.alerts ?? []).filter(
    (a) => a.level === 'critical' && a.kind !== 'stale' && a.kind !== 'degraded' && a.kind !== 'fallback',
  )

  return (
    <div>
      {conn.backendDown ? (
        <Banner tone="crit" icon={CloudOff} title="Backend unreachable">
          {s
            ? `showing the last data received ${fmtAgo(conn.sinceLastResponseS)}; retrying every 2 s`
            : 'no data received yet; retrying every 2 s'}
          {conn.errorCode ? <span className="ml-1 font-mono text-xs opacity-70">({conn.errorCode})</span> : null}
        </Banner>
      ) : null}
      {s?.degraded ? (
        <Banner tone="crit" icon={Unplug} title="Degraded">
          {s.degraded_reason ?? 'simulator sync failing'}; showing last good state from{' '}
          <span className="tnum font-medium">{fmtSeconds(conn.dataAgeS)}</span> ago
        </Banner>
      ) : null}
      {s?.stale ? (
        <Banner tone="warn" icon={Database} title="Stale data">
          the simulator flagged its last response as stale (X-Simulator-Stale); auto submissions are paused
        </Banner>
      ) : null}
      {s?.fallback ? (
        <Banner tone="warn" icon={FlaskConical} title="Fallback forecast">
          prediction service unavailable; forecasts use the uncalibrated baseline and recommendations are marked
          “fallback”
        </Banner>
      ) : null}
      {critical.map((a) => (
        <Banner key={a.id} tone="crit" icon={a.kind === 'no_route' ? OctagonAlert : TriangleAlert} title={a.message} />
      ))}
    </div>
  )
}
