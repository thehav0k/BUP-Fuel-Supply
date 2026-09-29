import { CircleCheck, OctagonAlert, TriangleAlert } from 'lucide-react'
import type { RiskLevel } from '@/api/types'
import { Badge } from '@/components/ui/badge'
import { riskTone } from '@/lib/tone'
import { cn } from '@/lib/utils'

const LABEL: Record<RiskLevel, string> = { low: 'Low', medium: 'Medium', high: 'High' }

export function RiskIcon({ level, className }: { level: RiskLevel; className?: string }) {
  const Icon = level === 'high' ? OctagonAlert : level === 'medium' ? TriangleAlert : CircleCheck
  return <Icon className={cn('size-3.5', className)} aria-hidden />
}

/** Risk level as icon + label (never color alone). Optional numeric score. */
export function RiskChip({
  level,
  score,
  size = 'default',
  className,
}: {
  level: RiskLevel
  score?: number
  size?: 'default' | 'sm' | 'lg'
  className?: string
}) {
  return (
    <Badge tone={riskTone(level)} size={size} className={className} title={score !== undefined ? `risk ${score.toFixed(2)}` : undefined}>
      <RiskIcon level={level} />
      {LABEL[level]}
      {score !== undefined ? <span className="tnum opacity-75">{score.toFixed(2)}</span> : null}
    </Badge>
  )
}
