import type { Recommendation } from '@/api/types'
import { AllocationStatusBadge, RecStatusBadge } from '@/components/StatusBadges'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { fmtLiters } from '@/lib/format'
import type { World } from '@/lib/world'

export function RecentRecommendations({ items, world }: { items: Recommendation[]; world: World }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Recent recommendations</CardTitle>
        <span className="text-xs text-muted-foreground">last {items.length}, not open</span>
      </CardHeader>
      <CardContent className="px-1.5 pb-2">
        {items.length === 0 ? (
          <div className="py-4 text-center text-xs text-muted-foreground">Nothing handled yet.</div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>ID</TH>
                <TH className="text-right">Tick</TH>
                <TH>Station · fuel</TH>
                <TH className="text-right">Qty</TH>
                <TH>Route</TH>
                <TH>Status</TH>
                <TH>Allocation</TH>
                <TH>Failure</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((r) => (
                <TR key={r.id}>
                  <TD className="font-mono text-xs">{r.id}</TD>
                  <TD className="text-right">{r.created_tick}</TD>
                  <TD>
                    {r.station_name} · <span className="text-xs font-medium">{r.fuel}</span>
                  </TD>
                  <TD className="text-right">{fmtLiters(r.quantity)}</TD>
                  <TD className="text-xs text-muted-foreground">
                    {world.routeLabel(r.route_id)}
                    {r.uses_backup_route ? ' (backup)' : ''}
                  </TD>
                  <TD>
                    <RecStatusBadge status={r.status} />
                  </TD>
                  <TD>
                    {r.allocation_id != null ? (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="text-xs">#{r.allocation_id}</span>
                        <AllocationStatusBadge status={r.allocation_status} />
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TD>
                  <TD className="max-w-72 text-xs">
                    {r.failure_code ? (
                      <span className="text-crit-ink" title={r.failure_message ?? undefined}>
                        <span className="font-mono font-semibold">{r.failure_code}</span>
                        {r.failure_message ? ` ${r.failure_message}` : ''}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
