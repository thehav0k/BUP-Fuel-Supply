import { Activity, FlaskConical, History, Lightbulb, Network, type LucideIcon } from 'lucide-react'
import { useHealthQuery, useStateQuery } from '@/api/queries'
import { href, type Screen } from '@/lib/router'
import { componentTone, toneFill } from '@/lib/tone'
import { cn } from '@/lib/utils'

const TABS: { screen: Screen; label: string; icon: LucideIcon }[] = [
  { screen: 'network', label: 'Network', icon: Network },
  { screen: 'recommendations', label: 'Recommendations', icon: Lightbulb },
  { screen: 'history', label: 'History & events', icon: History },
  { screen: 'health', label: 'System health', icon: Activity },
  { screen: 'demo', label: 'Demo control', icon: FlaskConical },
]

export function NavTabs({ current }: { current: Screen }) {
  const { data: s } = useStateQuery()
  const { data: health, isError: healthErr } = useHealthQuery()
  const openRecs = s?.counts.open_recommendations ?? 0
  const healthTone = healthErr ? 'crit' : health ? componentTone(health.status === 'ok' ? 'up' : 'degraded') : 'neutral'

  return (
    <nav className="flex items-end gap-1 overflow-x-auto px-3" aria-label="Screens">
      {TABS.map(({ screen, label, icon: Icon }) => {
        const active = screen === current
        return (
          <a
            key={screen}
            href={href(screen)}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'relative flex h-9 shrink-0 items-center gap-1.5 rounded-t-md px-3 text-[13px] font-medium transition-colors',
              active
                ? 'text-foreground after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-primary'
                : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
            )}
          >
            <Icon className="size-4" aria-hidden />
            {label}
            {screen === 'recommendations' && openRecs > 0 ? (
              <span className="tnum ml-0.5 rounded-full bg-primary px-1.5 text-[11px] font-semibold text-primary-foreground">
                {openRecs}
              </span>
            ) : null}
            {screen === 'health' ? (
              <span className={cn('ml-0.5 size-2 rounded-full', toneFill[healthTone])} aria-label={`health ${healthTone}`} />
            ) : null}
          </a>
        )
      })}
      {s ? (
        <div className="ml-auto hidden shrink-0 items-center gap-3 pb-2 text-xs text-muted-foreground md:flex">
          <span>
            <span className="tnum font-semibold text-foreground">{s.counts.pending_allocations}</span> pending
          </span>
          <span>
            <span className="tnum font-semibold text-foreground">{s.counts.in_transit_allocations}</span> in transit
          </span>
        </div>
      ) : null}
    </nav>
  )
}
