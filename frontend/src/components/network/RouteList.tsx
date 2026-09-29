import { CalendarClock, CircleCheck, CircleX, Route as RouteIcon } from 'lucide-react'
import type { RouteView } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { fmtLiters, fmtTickSpan } from '@/lib/format'
import type { World } from '@/lib/world'

export function RouteList({ routes, world }: { routes: RouteView[]; world: World }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2">
        <RouteIcon className="size-4 text-muted-foreground" aria-hidden />
        <CardTitle>Routes</CardTitle>
      </CardHeader>
      <CardContent className="px-1.5 pb-2">
        <Table>
          <THead>
            <TR className="hover:bg-transparent">
              <TH>Route</TH>
              <TH>Status</TH>
              <TH className="text-right">Transit</TH>
              <TH className="text-right">Max shipment</TH>
              <TH>Scheduled disruption</TH>
            </TR>
          </THead>
          <TBody>
            {routes.map((r) => {
              const upcoming =
                r.scheduled_disruption && (world.tick === null || r.scheduled_disruption.end_tick > world.tick)
                  ? r.scheduled_disruption
                  : null
              return (
                <TR key={r.id}>
                  <TD className="font-medium">
                    <div className="flex items-center gap-1.5">
                      {world.depotName(r.source_depot_id)} → {world.stationName(r.destination_station_id)}
                      {r.is_backup ? (
                        <Badge size="sm" tone="neutral">
                          Backup
                        </Badge>
                      ) : null}
                    </div>
                  </TD>
                  <TD>
                    {r.status === 'AVAILABLE' ? (
                      <Badge tone="ok">
                        <CircleCheck />
                        AVAILABLE
                      </Badge>
                    ) : (
                      <Badge tone="crit">
                        <CircleX />
                        DISRUPTED
                      </Badge>
                    )}
                  </TD>
                  <TD className="text-right text-muted-foreground">
                    {r.transit_ticks} ticks · {fmtTickSpan(r.transit_ticks, world.tickMinutes)}
                  </TD>
                  <TD className="text-right">{fmtLiters(r.max_shipment)}</TD>
                  <TD>
                    {upcoming ? (
                      <span className="inline-flex items-center gap-1 text-xs text-warn-ink">
                        <CalendarClock className="size-3.5" aria-hidden />
                        ticks {upcoming.start_tick}–{upcoming.end_tick}
                        {world.tick !== null && upcoming.start_tick > world.tick
                          ? ` (in ${upcoming.start_tick - world.tick})`
                          : ' (now)'}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TD>
                </TR>
              )
            })}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  )
}
