import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Recommendation } from '@/api/types'
import { AXIS_LINE, AXIS_TICK, GRID_STROKE, SERIES, tickClock, tickClockLong } from '@/lib/chart'
import { fmtLiters, fmtLitersCompact } from '@/lib/format'
import { ChartTooltipBody, LegendLine, type SeriesSpec } from './ChartTooltip'

const SPECS: SeriesSpec[] = [
  { key: 'with', name: 'with shipment', color: SERIES.withShipment, format: (v) => fmtLiters(v) },
  { key: 'without', name: 'without', color: SERIES.without, dashed: true, format: (v) => fmtLiters(v) },
]

/** PRD 9.4: projected station level over the next 24 ticks, with vs without this shipment. */
export function WhatIfChart({
  rec,
  capacity,
  tickMinutes,
}: {
  rec: Recommendation
  capacity: number | null
  tickMinutes: number
}) {
  const data = rec.what_if
  if (!data.length) {
    return <div className="py-4 text-center text-xs text-muted-foreground">No what-if projection for this recommendation.</div>
  }
  const arrival = rec.created_tick + rec.transit_ticks
  const first = data[0].tick
  const last = data[data.length - 1].tick
  return (
    <div>
      <div className="mb-0.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5">
        <span className="text-[11px] font-medium text-muted-foreground">What-if · next {data.length} ticks</span>
        <div className="flex gap-3">
          <LegendLine color={SERIES.withShipment} label="With" />
          <LegendLine color={SERIES.without} dashed label="Without" />
        </div>
      </div>
      <div className="h-32">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={GRID_STROKE} vertical={false} />
            <XAxis
              dataKey="tick"
              type="number"
              domain={[first, last]}
              tick={AXIS_TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              tickFormatter={(t: number) => tickClock(t, tickMinutes)}
              minTickGap={24}
            />
            <YAxis
              tick={AXIS_TICK}
              axisLine={false}
              tickLine={false}
              width={40}
              tickFormatter={(v: number) => fmtLitersCompact(v, false)}
              domain={[(min: number) => Math.min(0, min), (max: number) => Math.max(capacity ?? 0, max, 1)]}
            />
            {capacity ? (
              <ReferenceLine
                y={capacity}
                stroke={SERIES.capacity}
                strokeDasharray="4 3"
                label={{ value: 'capacity', position: 'insideTopRight', fill: 'var(--chart-axis)', fontSize: 10 }}
              />
            ) : null}
            <ReferenceLine y={0} stroke={SERIES.stockout} strokeDasharray="4 3" />
            {arrival >= first && arrival <= last ? (
              <ReferenceLine
                x={arrival}
                stroke="var(--chart-axis)"
                label={{ value: 'arrives', position: 'insideTopLeft', fill: 'var(--chart-axis)', fontSize: 10 }}
              />
            ) : null}
            <Tooltip
              cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
              isAnimationActive={false}
              content={(p) => (
                <ChartTooltipBody
                  active={p.active}
                  row={p.payload?.[0]?.payload as Record<string, unknown> | undefined}
                  title={`${tickClockLong(Number(p.label), tickMinutes)} · tick ${p.label}`}
                  series={SPECS}
                />
              )}
            />
            <Line dataKey="without" stroke={SERIES.without} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            <Line dataKey="with" stroke={SERIES.withShipment} strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
