import { Fuel, Pause, Play } from 'lucide-react'
import type { ReactNode } from 'react'
import { useConnection } from '@/api/connection'
import { useStateQuery } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { fmtLiters, fmtPct, fmtSeconds, fmtSimClock } from '@/lib/format'
import { serviceLevelTone, toneText } from '@/lib/tone'
import { cn } from '@/lib/utils'
import { ModeToggle } from './ModeToggle'

function Stat({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex min-w-0 flex-col justify-center', className)}>
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="truncate text-sm font-semibold leading-tight">{children}</span>
    </div>
  )
}

export function TopBar() {
  const { data: s } = useStateQuery()
  const conn = useConnection()
  const sl = s?.metrics?.service_level ?? null
  const slTone = serviceLevelTone(sl)
  const age = conn.dataAgeS
  const ageTone = age === null ? 'neutral' : age > 15 ? 'crit' : age > 6 ? 'warn' : 'neutral'

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
      <div className="flex items-center gap-2 pr-2">
        <div className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
          <Fuel className="size-4.5" aria-hidden />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-tight">FuelOps</div>
          <div className="text-[11px] text-muted-foreground">Supply operations console</div>
        </div>
      </div>

      <Stat label="Tick">
        <span className="tnum">{s?.tick ?? '—'}</span>
      </Stat>
      <Stat label="Sim time">
        <span className="tnum">{s ? fmtSimClock(s.tick, s.sim_time, s.ticks_per_hour, s.tick_minutes) : '—'}</span>
      </Stat>
      <div className="flex items-center">
        {s?.sim_status === 'RUNNING' ? (
          <Badge tone="ok" size="lg" className="font-semibold">
            <Play className="size-3.5!" aria-hidden />
            RUNNING
          </Badge>
        ) : s?.sim_status === 'PAUSED' ? (
          <Badge tone="warn" size="lg" className="font-semibold">
            <Pause className="size-3.5!" aria-hidden />
            PAUSED
          </Badge>
        ) : (
          <Badge tone="neutral" size="lg">
            NO SYNC
          </Badge>
        )}
      </div>

      <div className="flex flex-col justify-center">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Service level</span>
        <span className={cn('text-2xl font-bold leading-none', toneText[slTone])}>{sl === null ? '—' : fmtPct(sl, 2)}</span>
      </div>
      <Stat label="Unmet demand">
        <span className={cn('tnum', (s?.metrics?.unmet_demand_liters ?? 0) > 0 && 'text-crit-ink')}>
          {fmtLiters(s?.metrics?.unmet_demand_liters ?? null)}
        </span>
      </Stat>
      <Stat label="Data age">
        <span className={cn('tnum', toneText[ageTone])}>{age === null ? '—' : fmtSeconds(age)}</span>
      </Stat>

      <ModeToggle className="ml-auto" />
    </div>
  )
}
