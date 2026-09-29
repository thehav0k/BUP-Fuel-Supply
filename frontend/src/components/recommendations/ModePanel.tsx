import { useSettingsQuery, useStateQuery } from '@/api/queries'
import { ModeToggle } from '@/components/ModeToggle'
import { Card } from '@/components/ui/card'
import { MODE_INFO, MODES } from '@/lib/modes'
import { fmtPct } from '@/lib/format'
import { cn } from '@/lib/utils'

export function ModePanel() {
  const { data: s } = useStateQuery()
  const { data: settings } = useSettingsQuery()
  const mode = s?.mode
  return (
    <Card className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center">
      <div className="flex shrink-0 flex-col gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Decision mode</span>
        <ModeToggle className="items-start" />
      </div>
      <ul className="grid flex-1 gap-2 text-xs sm:grid-cols-3">
        {MODES.map((m) => (
          <li
            key={m}
            className={cn(
              'rounded-md px-2.5 py-1.5 ring-1 ring-inset',
              m === mode ? 'bg-series-1/10 ring-series-1/40' : 'ring-border text-muted-foreground',
            )}
          >
            <span className={cn('font-semibold', m === mode && 'text-info-ink')}>{MODE_INFO[m].label}</span>
            {m === mode ? <span className="ml-1 text-[10px] uppercase text-info-ink">active</span> : null}
            <div className="mt-0.5">
              {MODE_INFO[m].blurb}
              {m === 'hybrid' && settings
                ? ` Threshold: confidence ≥ ${fmtPct(settings.hybrid_min_confidence)}, risk ≤ ${settings.hybrid_max_risk.toFixed(2)}.`
                : ''}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
