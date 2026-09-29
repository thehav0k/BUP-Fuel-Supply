import { CircleCheck, CircleX } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Inline result line for a mutation: green check or red cross with CODE and message. */
export function ResultNote({
  ok,
  code,
  children,
  className,
}: {
  ok: boolean
  code?: string | null
  children?: ReactNode
  className?: string
}) {
  const Icon = ok ? CircleCheck : CircleX
  return (
    <div
      role={ok ? 'status' : 'alert'}
      className={cn(
        'flex items-start gap-1.5 rounded-md px-2 py-1.5 text-xs ring-1 ring-inset',
        ok ? 'bg-ok/10 text-ok-ink ring-ok/30' : 'bg-crit/10 text-crit-ink ring-crit/30',
        className,
      )}
    >
      <Icon className="mt-px size-3.5 shrink-0" aria-hidden />
      <div className="min-w-0 break-words">
        {code ? <span className="mr-1 font-mono font-semibold">{code}</span> : null}
        {children}
      </div>
    </div>
  )
}
