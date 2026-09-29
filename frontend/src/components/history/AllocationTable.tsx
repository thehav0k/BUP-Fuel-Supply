import { Ban, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { errorInfo } from '@/api/client'
import { useCancelAllocation } from '@/api/queries'
import type { Allocation } from '@/api/types'
import { ResultNote } from '@/components/ErrorNote'
import { AllocationStatusBadge } from '@/components/StatusBadges'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { fmtLiters } from '@/lib/format'
import type { World } from '@/lib/world'

interface CancelOutcome {
  id: number
  ok: boolean
  code: string | null
  message: string | null
}

export function AllocationTable({ items, world }: { items: Allocation[]; world: World }) {
  const cancel = useCancelAllocation()
  const [outcome, setOutcome] = useState<CancelOutcome | null>(null)

  const doCancel = (id: number) => {
    setOutcome(null)
    cancel
      .mutateAsync(id)
      .then((res) =>
        setOutcome({ id, ok: res.ok, code: res.error?.code ?? null, message: res.error?.message ?? null }),
      )
      .catch((err: unknown) => setOutcome({ id, ok: false, ...errorInfo(err) }))
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Allocations</CardTitle>
        <span className="text-xs text-muted-foreground">simulator allocations, newest first · PENDING ones can be cancelled</span>
      </CardHeader>
      <CardContent className="px-1.5 pb-2">
        {outcome ? (
          <div className="px-2.5 pb-2">
            <ResultNote ok={outcome.ok} code={outcome.code}>
              {outcome.ok ? `Allocation #${outcome.id} cancelled; the depot was refunded.` : `Cancel #${outcome.id} failed: ${outcome.message ?? ''}`}
            </ResultNote>
          </div>
        ) : null}
        {items.length === 0 ? (
          <div className="py-6 text-center text-xs text-muted-foreground">No allocations submitted yet.</div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH className="text-right">ID</TH>
                <TH>Route</TH>
                <TH>Fuel</TH>
                <TH className="text-right">Qty</TH>
                <TH className="text-right">Created</TH>
                <TH className="text-right">Departs</TH>
                <TH className="text-right">ETA</TH>
                <TH className="text-right">Arrived</TH>
                <TH>Status</TH>
                <TH>Failure</TH>
                <TH>Rec</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {items.map((a) => {
                const busy = cancel.isPending && cancel.variables === a.id
                return (
                  <TR key={a.id}>
                    <TD className="text-right font-medium">#{a.id}</TD>
                    <TD className="whitespace-nowrap">{world.routeLabel(a.route_id)}</TD>
                    <TD className="text-xs font-medium">{a.fuel_type}</TD>
                    <TD className="text-right whitespace-nowrap">{fmtLiters(a.quantity)}</TD>
                    <TD className="text-right">{a.created_tick}</TD>
                    <TD className="text-right">{a.departure_tick ?? '—'}</TD>
                    <TD className="text-right">{a.expected_arrival_tick ?? '—'}</TD>
                    <TD className="text-right">{a.actual_arrival_tick ?? '—'}</TD>
                    <TD>
                      <AllocationStatusBadge status={a.status} />
                    </TD>
                    <TD className="max-w-56 text-xs text-crit-ink">{a.failure_reason ?? <span className="text-muted-foreground">—</span>}</TD>
                    <TD className="font-mono text-xs text-muted-foreground">{a.recommendation_id ?? '—'}</TD>
                    <TD className="text-right">
                      {a.status === 'PENDING' ? (
                        <Button variant="outline" size="xs" onClick={() => doCancel(a.id)} disabled={busy}>
                          {busy ? <LoaderCircle className="animate-spin" /> : <Ban />}
                          Cancel
                        </Button>
                      ) : null}
                    </TD>
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
