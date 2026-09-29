import { useMemo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ForecastFuel } from '@/api/types'
import { AXIS_LINE, AXIS_TICK, GRID_STROKE, SERIES, tickClock, tickClockLong } from '@/lib/chart'
import { fmtInt, fmtLiters, fmtLitersCompact } from '@/lib/format'
import { ChartTooltipBody, LegendLine, type SeriesSpec } from './ChartTooltip'

interface Row {
  tick: number
  actual?: number
  forecastPast?: number
  forecastAhead?: number
  level?: number
  unmet?: number
}

const L = (v: number) => fmtLiters(v)

const DEMAND_SERIES: SeriesSpec[] = [
  { key: 'actual', name: 'actual demand', color: SERIES.actual, format: L },
  { key: 'forecastPast', name: 'our forecast (made 1 tick ahead)', color: SERIES.forecast, format: L },
  { key: 'forecastAhead', name: 'forecast ahead', color: SERIES.forecast, dashed: true, format: L },
  { key: 'unmet', name: 'unmet', color: SERIES.stockout, format: L },
]

const LEVEL_SERIES: SeriesSpec[] = [{ key: 'level', name: 'projected inventory', color: SERIES.level, format: L }]

function buildRows(f: ForecastFuel): { rows: Row[]; nowTick: number | null; minTick: number; maxTick: number } {
  const byTick = new Map<number, Row>()
  for (const h of f.history) {
    byTick.set(h.tick, {
      tick: h.tick,
      actual: h.actual,
      forecastPast: h.forecast ?? undefined,
      unmet: h.unmet > 0 ? h.unmet : undefined,
    })
  }
  for (const p of f.future) {
    const row = byTick.get(p.tick) ?? { tick: p.tick }
    row.forecastAhead = p.forecast
    row.level = p.projected_level
    byTick.set(p.tick, row)
  }
  const rows = [...byTick.values()].sort((a, b) => a.tick - b.tick)
  // Join the "forecast ahead" line onto the last historical point so the two read as one continuing line.
  const lastHist = f.history.length ? f.history[f.history.length - 1] : null
  if (lastHist && f.future.length) {
    const r = byTick.get(lastHist.tick)
    if (r && r.forecastAhead === undefined) r.forecastAhead = lastHist.forecast ?? lastHist.actual
  }
  const nowTick = f.future.length ? f.future[0].tick : lastHist ? lastHist.tick + 1 : null
  const minTick = rows.length ? rows[0].tick : 0
  const maxTick = rows.length ? rows[rows.length - 1].tick : 1
  return { rows, nowTick, minTick, maxTick }
}

/**
 * Actual vs forecast demand (history, out-of-sample), the forecast continuing
 * to the right, and, in a second panel on the same time axis, the projected
 * inventory level with the capacity line. Two panels instead of a dual axis so
 * each quantity keeps its own honest scale.
 */
export function ForecastChart({ fuel, tickMinutes }: { fuel: ForecastFuel; tickMinutes: number }) {
  const { rows, nowTick, minTick, maxTick } = useMemo(() => buildRows(fuel), [fuel])
  const syncId = `forecast-${fuel.fuel}`
  const xProps = {
    dataKey: 'tick',
    type: 'number' as const,
    domain: [minTick, maxTick] as [number, number],
    tick: AXIS_TICK,
    axisLine: AXIS_LINE,
    tickLine: false,
    tickFormatter: (t: number) => tickClock(t, tickMinutes),
    minTickGap: 28,
  }
  const yProps = {
    tick: AXIS_TICK,
    axisLine: false,
    tickLine: false,
    width: 44,
    tickFormatter: (v: number) => fmtLitersCompact(v, false),
  }
  const title = (t: number) => (
    <>
      {tickClockLong(t, tickMinutes)} <span className="opacity-70">· tick {t}</span>
      {nowTick !== null && t >= nowTick ? <span className="ml-1 opacity-70">(forecast)</span> : null}
    </>
  )

  if (!rows.length) {
    return <div className="py-10 text-center text-sm text-muted-foreground">No demand history for this fuel yet.</div>
  }

  return (
    <div className="flex flex-col gap-4">
      <section>
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h4 className="text-xs font-semibold">Demand per tick</h4>
          <div className="flex flex-wrap gap-3">
            <LegendLine color={SERIES.actual} label="Actual" />
            <LegendLine color={SERIES.forecast} label="Our forecast at the time" />
            <LegendLine color={SERIES.forecast} dashed label="Forecast ahead" />
          </div>
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} syncId={syncId} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              {nowTick !== null ? (
                <ReferenceArea x1={nowTick} x2={maxTick} fill="var(--muted)" fillOpacity={0.6} ifOverflow="hidden" />
              ) : null}
              <XAxis {...xProps} />
              <YAxis {...yProps} />
              {nowTick !== null ? (
                <ReferenceLine
                  x={nowTick}
                  stroke="var(--chart-axis)"
                  label={{ value: 'now', position: 'insideTopLeft', fill: 'var(--chart-axis)', fontSize: 11 }}
                />
              ) : null}
              <Tooltip
                cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
                isAnimationActive={false}
                content={(p) => (
                  <ChartTooltipBody
                    active={p.active}
                    row={p.payload?.[0]?.payload as Record<string, unknown> | undefined}
                    title={title(Number(p.label))}
                    series={DEMAND_SERIES}
                  />
                )}
              />
              <Line dataKey="actual" stroke={SERIES.actual} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
              <Line dataKey="forecastPast" stroke={SERIES.forecast} strokeWidth={2} dot={false} isAnimationActive={false} strokeOpacity={0.9} />
              <Line
                dataKey="forecastAhead"
                stroke={SERIES.forecast}
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h4 className="text-xs font-semibold">Projected inventory</h4>
          <div className="flex flex-wrap gap-3">
            <LegendLine color={SERIES.level} label="Projected level (incl. inbound)" />
            <LegendLine color={SERIES.capacity} dashed label={`Capacity ${fmtInt(fuel.capacity)} L`} />
            <LegendLine color={SERIES.stockout} dashed label="Stockout" />
          </div>
        </div>
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows} syncId={syncId} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis {...xProps} />
              <YAxis
                {...yProps}
                domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(fuel.capacity, max, 1)]}
              />
              <ReferenceLine y={fuel.capacity} stroke={SERIES.capacity} strokeDasharray="4 3" ifOverflow="extendDomain" />
              <ReferenceLine y={0} stroke={SERIES.stockout} strokeDasharray="4 3" />
              {nowTick !== null ? <ReferenceLine x={nowTick} stroke="var(--chart-axis)" /> : null}
              <Tooltip
                cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
                isAnimationActive={false}
                content={(p) => (
                  <ChartTooltipBody
                    active={p.active}
                    row={p.payload?.[0]?.payload as Record<string, unknown> | undefined}
                    title={title(Number(p.label))}
                    series={LEVEL_SERIES}
                    footer={`capacity ${fmtLiters(fuel.capacity)}`}
                  />
                )}
              />
              <Line dataKey="level" stroke={SERIES.level} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  )
}
