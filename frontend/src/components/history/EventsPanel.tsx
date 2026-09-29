import { CalendarClock, CircleCheck, Flame } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { SimEvent } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { humanize } from '@/lib/format'
import type { Tone } from '@/lib/tone'
import { cn } from '@/lib/utils'

const GROUPS: { status: SimEvent['status']; title: string; tone: Tone; icon: LucideIcon }[] = [
  { status: 'ACTIVE', title: 'Active', tone: 'crit', icon: Flame },
  { status: 'SCHEDULED', title: 'Scheduled', tone: 'warn', icon: CalendarClock },
  { status: 'RESOLVED', title: 'Resolved', tone: 'neutral', icon: CircleCheck },
]

function EventRow({ e, tick }: { e: SimEvent; tick: number | null }) {
  let when = `ticks ${e.start_tick} → ${e.end_tick}`
  if (tick !== null) {
    if (e.status === 'SCHEDULED') when += ` · starts in ${e.start_tick - tick}`
    else if (e.status === 'ACTIVE') when += ` · ${Math.max(0, e.end_tick - tick)} left`
  }
  return (
    <li className="flex flex-col gap-0.5 border-b py-2 last:border-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{humanize(e.type)}</span>
        <span className="font-mono text-[11px] text-muted-foreground">#{e.id}</span>
        <span className="tnum ml-auto text-[11px] text-muted-foreground">{when}</span>
      </div>
      <div className="text-xs text-muted-foreground">{e.description}</div>
    </li>
  )
}

export function EventsPanel({ items, tick }: { items: SimEvent[]; tick: number | null }) {
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {GROUPS.map((g) => {
        const list = items
          .filter((e) => e.status === g.status)
          .sort((a, b) => (g.status === 'RESOLVED' ? b.end_tick - a.end_tick : a.start_tick - b.start_tick))
        return (
          <Card key={g.status} className={cn(g.status === 'ACTIVE' && list.length > 0 && 'border-crit/40')}>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-1.5">
                <g.icon className="size-4 text-muted-foreground" aria-hidden />
                {g.title} events
              </CardTitle>
              <Badge tone={list.length ? g.tone : 'neutral'}>{list.length}</Badge>
            </CardHeader>
            <CardContent>
              {list.length === 0 ? (
                <div className="py-3 text-center text-xs text-muted-foreground">None</div>
              ) : (
                <ul className={cn(g.status === 'RESOLVED' && 'max-h-96 overflow-y-auto')}>
                  {list.map((e) => (
                    <EventRow key={e.id} e={e} tick={tick} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
