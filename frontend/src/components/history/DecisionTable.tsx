import { Bot, Cog, User } from 'lucide-react'
import type { Decision } from '@/api/types'
import { AllocationStatusBadge, DecisionActionBadge } from '@/components/StatusBadges'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { useNow } from '@/lib/clock'
import { fmtClock, fmtDateTime, fmtLiters, fmtRelative } from '@/lib/format'
import type { World } from '@/lib/world'

const ACTOR_ICON = { operator: User, auto: Bot, system: Cog } as const

export function DecisionTable({ items, world }: { items: Decision[]; world: World }) {
  const now = useNow()
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Decision log</CardTitle>
        <span className="text-xs text-muted-foreground">newest first · allocation status is live</span>
      </CardHeader>
      <CardContent className="px-1.5 pb-2">
        {items.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted-foreground">
            No decisions yet. Approvals, rejections, auto submissions and expiries are logged here.
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Time</TH>
                <TH className="text-right">Tick</TH>
                <TH>Action</TH>
                <TH>Actor</TH>
                <TH>Station · fuel</TH>
                <TH className="text-right">Qty</TH>
                <TH>Route</TH>
                <TH>Allocation</TH>
                <TH>Status</TH>
                <TH>Failure</TH>
                <TH>Note</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((d) => {
                const ActorIcon = ACTOR_ICON[d.actor] ?? Cog
                return (
                  <TR key={d.id}>
                    <TD className="whitespace-nowrap" title={fmtDateTime(d.created_at)}>
                      <div>{fmtClock(d.created_at)}</div>
                      <div className="text-[11px] text-muted-foreground">{fmtRelative(d.created_at, now)}</div>
                    </TD>
                    <TD className="text-right">{d.tick ?? '—'}</TD>
                    <TD>
                      <DecisionActionBadge action={d.action} />
                    </TD>
                    <TD>
                      <span className="inline-flex items-center gap-1 text-xs">
                        <ActorIcon className="size-3.5 text-muted-foreground" aria-hidden />
                        {d.actor}
                      </span>
                    </TD>
                    <TD className="whitespace-nowrap">
                      {world.stationName(d.station_id)} · <span className="text-xs font-medium">{d.fuel}</span>
                    </TD>
                    <TD className="text-right whitespace-nowrap">{fmtLiters(d.quantity)}</TD>
                    <TD className="text-xs whitespace-nowrap text-muted-foreground">{world.routeLabel(d.route_id)}</TD>
                    <TD className="text-xs">{d.allocation_id != null ? `#${d.allocation_id}` : '—'}</TD>
                    <TD>
                      <AllocationStatusBadge status={d.allocation_status} />
                    </TD>
                    <TD className="max-w-64 text-xs">
                      {d.failure_code || d.failure_reason ? (
                        <span className="text-crit-ink">
                          {d.failure_code ? <span className="font-mono font-semibold">{d.failure_code}</span> : null}
                          {d.failure_reason ? ` ${d.failure_reason}` : ''}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TD>
                    <TD className="max-w-56 text-xs text-muted-foreground">{d.note || '—'}</TD>
                  </TR>
                )
              })}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
