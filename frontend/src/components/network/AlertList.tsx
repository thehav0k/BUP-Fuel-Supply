import { Info, OctagonAlert, TriangleAlert } from 'lucide-react'
import type { Alert } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const ORDER = { critical: 0, warning: 1, info: 2 } as const

export function AlertList({ alerts }: { alerts: Alert[] }) {
  const sorted = [...alerts].sort((a, b) => ORDER[a.level] - ORDER[b.level])
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Alerts</CardTitle>
        <span className="tnum text-xs text-muted-foreground">{alerts.length}</span>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5">
        {sorted.length === 0 ? (
          <div className="py-3 text-center text-xs text-muted-foreground">No active alerts.</div>
        ) : (
          sorted.map((a) => {
            const Icon = a.level === 'critical' ? OctagonAlert : a.level === 'warning' ? TriangleAlert : Info
            return (
              <div
                key={a.id}
                className={cn(
                  'flex items-start gap-2 rounded-md px-2 py-1.5 text-xs ring-1 ring-inset',
                  a.level === 'critical'
                    ? 'bg-crit/10 text-crit-ink ring-crit/30'
                    : a.level === 'warning'
                      ? 'bg-warn/12 text-warn-ink ring-warn/35'
                      : 'bg-muted text-muted-foreground ring-border',
                )}
              >
                <Icon className="mt-px size-3.5 shrink-0" aria-hidden />
                <span className="text-foreground/90">{a.message}</span>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}
