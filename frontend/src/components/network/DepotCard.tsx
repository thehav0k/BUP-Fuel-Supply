import { Truck, Warehouse } from 'lucide-react'
import type { DepotFuelView, DepotView } from '@/api/types'
import { Meter } from '@/components/Meter'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { fmtHours, fmtInt, fmtLiters, fmtLitersCompact, fmtPct100 } from '@/lib/format'
import type { Tone } from '@/lib/tone'
import type { World } from '@/lib/world'

function depotFuelTone(f: DepotFuelView): Tone {
  if (f.fill_pct < 10) return 'crit'
  if (f.fill_pct < 25) return 'warn'
  return 'info'
}

function DepotFuelRow({ f }: { f: DepotFuelView }) {
  const a = f.next_arrival
  return (
    <div className="flex flex-col gap-1 py-1.5">
      <div className="flex items-baseline gap-2 text-xs">
        <span className="w-14 font-semibold tracking-wide">{f.fuel}</span>
        <span className="tnum text-muted-foreground">
          {fmtInt(f.inventory)} / {fmtLiters(f.capacity)}
        </span>
        <span className="tnum ml-auto font-medium">{fmtPct100(f.fill_pct)}</span>
      </div>
      <Meter
        value={f.inventory}
        max={f.capacity}
        tone={depotFuelTone(f)}
        marker={f.reserve_liters}
        height="h-2"
        label={`${f.fuel} depot inventory`}
      />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
        {a ? (
          <span className="inline-flex items-center gap-1">
            <Truck className="size-3.5" aria-hidden />
            <span className="tnum">
              +{fmtLitersCompact(a.quantity)} in {fmtHours(a.in_hours)} (tick {a.tick})
            </span>
            {a.status === 'DELAYED' ? (
              <Badge tone="crit" size="sm">
                Delayed
              </Badge>
            ) : null}
          </span>
        ) : (
          <span>no supply scheduled</span>
        )}
        <span className="tnum" title="Held back for this depot's own at-risk stations until the next arrival">
          reserve {fmtLitersCompact(f.reserve_liters)}
        </span>
        <span className="tnum" title="Inventory plus scheduled arrivals within the horizon (no outbound assumed)">
          proj. {fmtLitersCompact(f.projected_level_end)}
        </span>
      </div>
    </div>
  )
}

export function DepotCard({ depot, world }: { depot: DepotView; world: World }) {
  const usedPct = depot.dispatch_capacity_per_tick > 0 ? depot.dispatch_used_this_tick / depot.dispatch_capacity_per_tick : 0
  return (
    <Card>
      <CardHeader className="pb-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Warehouse className="size-4 text-muted-foreground" aria-hidden />
            <div>
              <h3 className="text-sm font-semibold leading-tight">{depot.name}</h3>
              <div className="text-xs text-muted-foreground">Depot · {world.regionName(depot.region_id)}</div>
            </div>
          </div>
          <Badge tone={depot.status === 'OPEN' ? 'ok' : 'warn'}>{depot.status}</Badge>
        </div>
        <div className="mt-1.5 flex flex-col gap-1">
          <div className="flex items-baseline justify-between text-[11px] text-muted-foreground">
            <span>Dispatch this tick</span>
            <span className="tnum">
              <span className="font-semibold text-foreground">{fmtInt(depot.dispatch_used_this_tick)}</span> /{' '}
              {fmtLiters(depot.dispatch_capacity_per_tick)}
            </span>
          </div>
          <Meter
            value={depot.dispatch_used_this_tick}
            max={depot.dispatch_capacity_per_tick}
            tone={usedPct >= 0.95 ? 'warn' : 'info'}
            height="h-1.5"
            label="dispatch capacity used this tick"
          />
        </div>
      </CardHeader>
      <CardContent className="divide-y pb-2">
        {depot.fuels.map((f) => (
          <DepotFuelRow key={f.fuel} f={f} />
        ))}
      </CardContent>
    </Card>
  )
}
