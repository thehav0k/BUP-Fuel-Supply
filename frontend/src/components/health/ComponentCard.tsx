import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Component } from '@/api/types'
import { ComponentStatusBadge } from '@/components/StatusBadges'
import { Card } from '@/components/ui/card'
import { useNow } from '@/lib/clock'
import { fmtRelative } from '@/lib/format'
import { componentTone, toneFill } from '@/lib/tone'
import { cn } from '@/lib/utils'

export function KV({ k, children, tone }: { k: string; children: ReactNode; tone?: 'crit' | 'warn' | 'ok' }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5 text-xs">
      <span className="text-muted-foreground">{k}</span>
      <span
        className={cn(
          'tnum text-right font-medium',
          tone === 'crit' && 'text-crit-ink',
          tone === 'warn' && 'text-warn-ink',
          tone === 'ok' && 'text-ok-ink',
        )}
      >
        {children}
      </span>
    </div>
  )
}

export function ComponentCard({
  title,
  icon: Icon,
  component,
  children,
}: {
  title: string
  icon: LucideIcon
  component: Component
  children?: ReactNode
}) {
  const now = useNow()
  const tone = componentTone(component.status)
  return (
    <Card className="relative overflow-hidden">
      <div className={cn('absolute inset-x-0 top-0 h-1', toneFill[tone])} aria-hidden />
      <div className="flex flex-col gap-2 p-4 pt-4.5">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Icon className="size-4.5 text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">{title}</h3>
          </div>
          <ComponentStatusBadge status={component.status} />
        </div>
        <p className="min-h-8 text-xs text-foreground/80">{component.detail || '—'}</p>
        <div className="divide-y border-t pt-1">
          {children}
          <KV k="Last OK">{component.last_ok_at ? fmtRelative(component.last_ok_at, now) : 'never'}</KV>
        </div>
      </div>
    </Card>
  )
}
