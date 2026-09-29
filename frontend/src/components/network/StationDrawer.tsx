import { FlaskConical, Truck } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { errorInfo } from '@/api/client'
import { useForecastQuery } from '@/api/queries'
import type { Fuel, StationView } from '@/api/types'
import { ForecastChart } from '@/components/charts/ForecastChart'
import { EmptyState } from '@/components/EmptyState'
import { ResultNote } from '@/components/ErrorNote'
import { RiskChip } from '@/components/RiskChip'
import { Badge } from '@/components/ui/badge'
import { Segmented } from '@/components/ui/segmented'
import { Sheet } from '@/components/ui/sheet'
import { Table, TBody, TD, TH, THead, TR } from '@/components/ui/table'
import { fmtHours, fmtLiters, fmtMultiplier, fmtPct, fmtPct100 } from '@/lib/format'
import { FUELS, type World } from '@/lib/world'

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-md border bg-card px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="tnum text-sm font-semibold">{value}</div>
    </div>
  )
}

export function StationDrawer({
  station,
  stationId,
  world,
  onClose,
}: {
  station: StationView | undefined
  stationId: string | null
  world: World
  onClose: () => void
}) {
  const [fuel, setFuel] = useState<Fuel>('DIESEL')
  const q = useForecastQuery(stationId)
  const ff = q.data?.fuels.find((f) => f.fuel === fuel)
  const fv = station?.fuels.find((f) => f.fuel === fuel)

  return (
    <Sheet
      open={!!stationId}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          {station?.name ?? world.stationName(stationId)}
          {station?.status === 'OUTAGE' ? <Badge tone="crit">OUTAGE</Badge> : null}
          {q.data?.fallback ? (
            <Badge tone="warn">
              <FlaskConical />
              fallback forecast
            </Badge>
          ) : null}
        </span>
      }
      description={
        station
          ? `${world.regionName(station.region_id)} · ${station.demand_profile.replace(/_/g, ' ')} · demand ${fmtMultiplier(station.demand_multiplier)} · actual vs forecast (out-of-sample)`
          : 'Actual vs forecast demand'
      }
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Segmented<Fuel>
          ariaLabel="Fuel"
          value={fuel}
          onChange={setFuel}
          options={FUELS.map((f) => ({ value: f, label: f }))}
        />
        {q.isFetching && q.data ? <span className="text-[11px] text-muted-foreground">refreshing…</span> : null}
      </div>

      {fv ? (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="Inventory" value={`${fmtLiters(fv.inventory)} (${fmtPct100(fv.fill_pct)})`} />
          <Stat label="Stockout in" value={fmtHours(fv.hours_to_stockout, world.horizonHours)} />
          <Stat label="Risk" value={<RiskChip level={fv.risk_level} score={fv.risk} />} />
          <Stat label="Next hour forecast" value={fmtLiters(fv.forecast_next_hour)} />
          <Stat label="Calibration" value={`×${(ff?.calibration_ratio ?? fv.calibration_ratio).toFixed(2)}`} />
          <Stat label="Confidence" value={fmtPct(ff?.confidence ?? fv.confidence)} />
          <Stat label="Lead time" value={`${fv.lead_time_ticks} ticks`} />
          <Stat label="Inbound" value={fmtLiters(fv.inbound_liters)} />
        </div>
      ) : null}

      {q.isPending ? (
        <EmptyState spin title="Loading forecast…" />
      ) : q.isError && !q.data ? (
        <ResultNote ok={false} code={errorInfo(q.error).code}>
          {errorInfo(q.error).message}
        </ResultNote>
      ) : ff ? (
        <ForecastChart fuel={ff} tickMinutes={q.data?.tick_minutes ?? world.tickMinutes} />
      ) : (
        <EmptyState title="No forecast for this fuel" />
      )}

      {fv && fv.inbound.length > 0 ? (
        <div className="mt-5">
          <h4 className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
            <Truck className="size-3.5" aria-hidden /> Inbound {fuel.toLowerCase()}
          </h4>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Allocation</TH>
                <TH>Route</TH>
                <TH className="text-right">Quantity</TH>
                <TH className="text-right">ETA tick</TH>
                <TH>Status</TH>
              </TR>
            </THead>
            <TBody>
              {fv.inbound.map((i) => (
                <TR key={i.allocation_id}>
                  <TD>#{i.allocation_id}</TD>
                  <TD>{world.routeLabel(i.route_id)}</TD>
                  <TD className="text-right">{fmtLiters(i.quantity)}</TD>
                  <TD className="text-right">{i.eta_tick ?? '—'}</TD>
                  <TD className="text-xs">{i.status}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      ) : null}

      {ff && ff.future.length > 0 ? (
        <details className="mt-5 text-xs">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Forecast table (next {ff.future.length} ticks)</summary>
          <div className="mt-2 max-h-72 overflow-y-auto">
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Tick</TH>
                  <TH>Sim time</TH>
                  <TH className="text-right">Forecast demand</TH>
                  <TH className="text-right">Projected level</TH>
                </TR>
              </THead>
              <TBody>
                {ff.future.map((p) => (
                  <TR key={p.tick}>
                    <TD>{p.tick}</TD>
                    <TD>{p.sim_time.replace('T', ' ').slice(0, 16)}</TD>
                    <TD className="text-right">{fmtLiters(p.forecast)}</TD>
                    <TD className="text-right">{fmtLiters(p.projected_level)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </div>
        </details>
      ) : null}
    </Sheet>
  )
}
