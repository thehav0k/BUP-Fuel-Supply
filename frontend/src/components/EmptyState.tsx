import { LoaderCircle, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export function EmptyState({
  icon: Icon = LoaderCircle,
  title,
  children,
  spin,
  className,
}: {
  icon?: LucideIcon
  title: ReactNode
  children?: ReactNode
  spin?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center',
        className,
      )}
    >
      <Icon className={cn('size-6 text-muted-foreground', spin && 'animate-spin')} aria-hidden />
      <div className="text-sm font-medium">{title}</div>
      {children ? <div className="max-w-md text-xs text-muted-foreground">{children}</div> : null}
    </div>
  )
}

/** The standard "no data yet" placeholder used before the first backend sync. */
export function WaitingForSync({ className, detail }: { className?: string; detail?: ReactNode }) {
  return (
    <EmptyState spin title="Waiting for first sync…" className={className}>
      {detail ?? 'The backend has not completed a sync with the simulator yet. This view fills in automatically.'}
    </EmptyState>
  )
}
