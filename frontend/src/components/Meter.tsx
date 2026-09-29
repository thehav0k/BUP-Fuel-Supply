import { cn } from '@/lib/utils'
import { toneFill, type Tone } from '@/lib/tone'

/**
 * Horizontal level meter: filled segment for the current value, an optional
 * lighter extension for inbound quantity, on a track that represents capacity.
 * Segments are separated by a 2px surface gap (not a border).
 */
export function Meter({
  value,
  extra = 0,
  max,
  tone,
  height = 'h-2.5',
  marker,
  label,
  className,
}: {
  value: number
  extra?: number
  max: number
  tone: Tone
  height?: string
  /** optional tick mark (e.g. reserve level) as a value on the same scale */
  marker?: number | null
  label?: string
  className?: string
}) {
  const safeMax = max > 0 ? max : 1
  const v = Math.max(0, Math.min(value, safeMax))
  const e = Math.max(0, Math.min(extra, safeMax - v))
  const vPct = (v / safeMax) * 100
  const ePct = (e / safeMax) * 100
  const mPct = marker != null && marker > 0 ? Math.min(100, (marker / safeMax) * 100) : null
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={v}
      aria-label={label}
      className={cn('relative w-full overflow-hidden rounded-full bg-muted ring-1 ring-inset ring-border/60', height, className)}
    >
      <div className="absolute inset-y-0 left-0 flex" style={{ width: `${vPct + ePct}%` }}>
        {vPct > 0 ? (
          <div className={cn('h-full rounded-l-full', ePct > 0 ? '' : 'rounded-r-full', toneFill[tone])} style={{ width: `${(vPct / (vPct + ePct)) * 100}%` }} />
        ) : null}
        {ePct > 0 ? (
          <div
            className={cn('h-full rounded-r-full opacity-35', vPct > 0 ? 'ml-[2px]' : 'rounded-l-full', toneFill[tone])}
            style={{ width: `${(ePct / (vPct + ePct)) * 100}%` }}
          />
        ) : null}
      </div>
      {mPct !== null ? (
        <div className="absolute inset-y-0 w-px bg-foreground/60" style={{ left: `${mPct}%` }} aria-hidden />
      ) : null}
    </div>
  )
}
