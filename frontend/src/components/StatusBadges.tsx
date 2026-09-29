import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleX,
  Clock,
  Hand,
  Loader,
  Truck,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { ComponentStatus } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { humanize } from '@/lib/format'
import { allocationTone, componentTone, decisionTone, recStatusTone } from '@/lib/tone'

const ALLOC_ICON: Record<string, LucideIcon> = {
  PENDING: Clock,
  IN_TRANSIT: Truck,
  ARRIVED: CircleCheck,
  FAILED: CircleX,
  CANCELLED: Ban,
}

export function AllocationStatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-muted-foreground">—</span>
  const Icon = ALLOC_ICON[status] ?? CircleDashed
  return (
    <Badge tone={allocationTone(status)}>
      <Icon />
      {status.replace('_', ' ')}
    </Badge>
  )
}

export function RecStatusBadge({ status }: { status: string }) {
  const Icon = status === 'SUBMITTING' ? Loader : status === 'SUBMITTED' ? CircleCheck : status === 'FAILED' ? CircleX : null
  return (
    <Badge tone={recStatusTone(status)} size="sm">
      {Icon ? <Icon /> : null}
      {status}
    </Badge>
  )
}

const DECISION_ICON: Record<string, LucideIcon> = {
  approved: CircleCheck,
  auto: Zap,
  rejected: Hand,
  expired: Clock,
  failed: CircleX,
  superseded: CircleDashed,
  cancelled: Ban,
}

export function DecisionActionBadge({ action }: { action: string }) {
  const Icon = DECISION_ICON[action] ?? CircleDashed
  return (
    <Badge tone={decisionTone(action)}>
      <Icon />
      {humanize(action)}
    </Badge>
  )
}

export function ComponentStatusBadge({ status, size = 'default' }: { status: ComponentStatus | string; size?: 'default' | 'lg' }) {
  const tone = componentTone(status)
  const Icon = tone === 'ok' ? CircleCheck : tone === 'warn' ? Clock : CircleX
  return (
    <Badge tone={tone} size={size}>
      <Icon />
      {String(status).toUpperCase()}
    </Badge>
  )
}
