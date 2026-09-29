import { CalendarClock, ChevronRight, PowerOff, Zap } from 'lucide-react'
import type { FuelView, StationView } from '@/api/types'
import { Meter } from '@/components/Meter'
import { RiskChip } from '@/components/RiskChip'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { fmtHours, fmtInt, fmtLiters, fmtMultiplier, fmtPct, fmtPct100 } from '@/lib/format'
import { riskTone, toneFill, toneText, worstRisk } from '@/lib/tone'
import { cn } from '@/lib/utils'
import type { World } from '@/lib/world'

function FuelRow({ f, horizonHours }: { f: FuelView; horizonHours: number }) {
  const tone = riskTone(f.risk_level)
  return (
    <div className="flex flex-col gap-1 py-1.5">
      <div className="flex items-center gap-2 text-xs">
        <span className="w-14 font-semibold tracking-wide">{f.fuel}</span>
        <span className="tnum w-9 text-right text-muted-foreground">{fmtPct100(f.fill_pct)}</span>
        <span
          className={cn('tnum flex-1 whitespace-nowrap', f.hours_to_stockout !== null ? toneText[tone] : 'text-muted-foreground')}
          title={f.ticks_to_stockout !== null ? `${f.ticks_to_stockout} ticks to stockout` : 'no stockout within the forecast horizon'}
        >
          {f.hours_to_stockout !== null ? `stockout in ${fmtHours(f.hours_to_stockout)}` : `${fmtHours(null, horizonHours)} cover`}
        </span>
        {f.spike ? (
          <span className="text-warn-ink" title={f.spike_reason ?? 'demand spike detected'}>
            <Zap className="size-3.5" aria-label="spike" />
          </span>
        ) : null}
        <RiskChip level={f.risk_level} size="sm" />
      </div>
      <Meter
        value={f.inventory}
        extra={f.inbound_liters}
        max={f.capacity}
        tone={tone}
        label={`${f.fuel} inventory ${fmtInt(f.inventory)} of ${fmtInt(f.capacity)} liters`}
      />
      <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
        <span className="tnum">
          {fmtInt(f.inventory)} / {fmtLiters(f.capacity)}
        </span>
        {f.inbound_liters > 0 ? <span className="tnum">+{fmtLiters(f.inbound_liters)} inbound</span> : null}
        <span className="tnum ml-auto">conf {fmtPct(f.confidence)}</span>
      </div>
    </div>
  )
}

export function StationCard({
  station,
  world,
  onOpen,
  selected,
}: {
  station: StationView
  world: World
  onOpen: (id: string) => void
  selected?: boolean
}) {
  const worst = worstRisk(station.fuels.map((f) => f.risk_level))
  const outage = station.status === 'OUTAGE'
  const upcoming = station.upcoming_spike
  return (
    <Card
      role="button"
      tabIndex={0}
      aria-label={`${station.name}: open forecast`}
      onClick={() => onOpen(station.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(station.id)
        }
      }}
      className={cn(
        'group relative cursor-pointer overflow-hidden transition-shadow hover:shadow-md',
        selected && 'ring-2 ring-ring',
        outage && 'border-crit/50',
      )}
    >
      <div className={cn('absolute inset-y-0 left-0 w-1', outage ? 'bg-crit' : toneFill[riskTone(worst)])} aria-hidden />
      <div className="px-4 pt-3 pb-2 pl-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h3 className="truncate text-[15px] font-semibold">{station.name}</h3>
              <ChevronRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
            </div>
            <div className="text-xs text-muted-foreground">
              {world.regionName(station.region_id)} · {station.demand_profile.replace(/_/g, ' ')}
            </div>
          </div>
          {outage ? (
            <Badge tone="crit" size="lg" className="font-bold">
              <PowerOff className="size-3.5!" />
              OUTAGE
            </Badge>
          ) : (
            <Badge tone="ok">OPEN</Badge>
          )}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Demand</span>
          <span className={cn('tnum font-semibold', station.demand_multiplier > 1 && 'text-warn-ink')}>
            {fmtMultiplier(station.demand_multiplier)}
          </span>
          {station.spike ? (
            <Badge tone="warn" size="sm">
              <Zap />
              Spike
            </Badge>
          ) : null}
          {upcoming ? (
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <CalendarClock className="size-3.5" aria-hidden />
              spike {fmtMultiplier(upcoming.multiplier)} scheduled at tick {upcoming.start_tick}
              {world.tick !== null && upcoming.start_tick > world.tick ? ` (in ${upcoming.start_tick - world.tick} ticks)` : ''}
            </span>
          ) : null}
        </div>
        {outage ? (
          <div className="mt-2 rounded-md bg-crit/10 px-2 py-1 text-[11px] font-medium text-crit-ink">
            Station closed: serves no demand and is excluded from allocation.
          </div>
        ) : null}
      </div>
      <div className="divide-y px-4 pb-2 pl-5">
        {station.fuels.map((f) => (
          <FuelRow key={f.fuel} f={f} horizonHours={world.horizonHours} />
        ))}
      </div>
    </Card>
  )
}
