import type { ReactNode } from 'react'

export interface SeriesSpec {
  key: string
  name: string
  color: string
  dashed?: boolean
  format: (v: number) => string
}

/**
 * Tooltip body: one readout listing every series at the hovered X.
 * Values lead (strong), series names follow; series are keyed by a short line.
 */
export function ChartTooltipBody({
  active,
  row,
  title,
  series,
  footer,
}: {
  active: boolean | undefined
  row: Record<string, unknown> | undefined
  title: ReactNode
  series: SeriesSpec[]
  footer?: ReactNode
}) {
  if (!active || !row) return null
  const items = series.filter((s) => typeof row[s.key] === 'number')
  if (!items.length && !footer) return null
  return (
    <div className="min-w-40 rounded-md border bg-popover px-2.5 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-muted-foreground">{title}</div>
      <div className="flex flex-col gap-0.5">
        {items.map((s) => (
          <div key={s.key} className="flex items-center gap-2">
            <svg width="14" height="4" aria-hidden className="shrink-0">
              <line x1="0" y1="2" x2="14" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? '3 2' : undefined} />
            </svg>
            <span className="tnum font-semibold">{s.format(row[s.key] as number)}</span>
            <span className="text-muted-foreground">{s.name}</span>
          </div>
        ))}
      </div>
      {footer ? <div className="mt-1 border-t pt-1 text-muted-foreground">{footer}</div> : null}
    </div>
  )
}

/** Legend entry mirroring the mark: a short line for line series. */
export function LegendLine({ color, dashed, label }: { color: string; dashed?: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <svg width="16" height="4" aria-hidden>
        <line x1="0" y1="2" x2="16" y2="2" stroke={color} strokeWidth="2" strokeDasharray={dashed ? '4 3' : undefined} />
      </svg>
      {label}
    </span>
  )
}
