/** Shared Recharts styling so every chart reads as one system. */
export const AXIS_TICK = { fill: 'var(--chart-axis)', fontSize: 11 } as const
export const AXIS_LINE = { stroke: 'var(--chart-grid)' } as const
export const GRID_STROKE = 'var(--chart-grid)'

export const SERIES = {
  actual: 'var(--series-1)',
  forecast: 'var(--series-2)',
  level: 'var(--series-3)',
  withShipment: 'var(--series-1)',
  without: 'var(--series-2)',
  capacity: 'var(--chart-axis)',
  stockout: 'var(--crit)',
} as const

/** Tick number -> "HH:MM" of simulated day (sim starts at 00:00 on day 1). Midnight shows "Day N". */
export function tickClock(tick: number, tickMinutes: number): string {
  const mins = Math.round(tick * tickMinutes)
  const dayMins = ((mins % 1440) + 1440) % 1440
  if (dayMins === 0) return `Day ${Math.floor(mins / 1440) + 1}`
  const h = String(Math.floor(dayMins / 60)).padStart(2, '0')
  const m = String(dayMins % 60).padStart(2, '0')
  return `${h}:${m}`
}

export function tickClockLong(tick: number, tickMinutes: number): string {
  const mins = Math.round(tick * tickMinutes)
  const day = Math.floor(mins / 1440) + 1
  const dayMins = ((mins % 1440) + 1440) % 1440
  const h = String(Math.floor(dayMins / 60)).padStart(2, '0')
  const m = String(dayMins % 60).padStart(2, '0')
  return `Day ${day} · ${h}:${m}`
}
