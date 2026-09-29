import { ArrowRight, Bot, Check, FlaskConical, Hourglass, LoaderCircle, Route as RouteIcon, Sparkles, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { Recommendation } from '@/api/types'
import { WhatIfChart } from '@/components/charts/WhatIfChart'
import { ResultNote } from '@/components/ErrorNote'
import { RiskChip } from '@/components/RiskChip'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { fmtHours, fmtLiters, fmtPct, fmtTickSpan, ticksToHours } from '@/lib/format'
import { riskTone, toneFill } from '@/lib/tone'
import { cn } from '@/lib/utils'
import type { World } from '@/lib/world'
import type { ActionOutcome } from './outcome'

function BeforeAfter({ label, before, after }: { label: string; before: ReactNode; after: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5">
        {before}
        <ArrowRight className="size-3.5 text-muted-foreground" aria-label="to" />
        {after}
      </div>
    </div>
  )
}

export function OutcomeNote({ outcome }: { outcome: ActionOutcome }) {
  if (!outcome.ok) {
    return (
      <ResultNote ok={false} code={outcome.code}>
        {outcome.action === 'approve' ? 'Approve failed: ' : 'Reject failed: '}
        {outcome.message}
      </ResultNote>
    )
  }
  const rec = outcome.rec
  if (outcome.action === 'reject') {
    return <ResultNote ok>Rejected{outcome.note ? ` (“${outcome.note}”)` : ''}.</ResultNote>
  }
  return (
    <ResultNote ok>
      Submitted{rec?.allocation_id != null ? ` as allocation #${rec.allocation_id}` : ''}
      {rec?.allocation_status ? ` (${rec.allocation_status})` : rec ? ` (${rec.status})` : ''}.
    </ResultNote>
  )
}

export function RecommendationCard({
  rec,
  world,
  tick,
  capacity,
  pending,
  outcome,
  onApprove,
  onReject,
}: {
  rec: Recommendation
  world: World
  tick: number | null
  capacity: number | null
  pending: boolean
  outcome: ActionOutcome | undefined
  onApprove: () => void
  onReject: (note: string) => void
}) {
  const [rejecting, setRejecting] = useState(false)
  const [note, setNote] = useState('')
  const expiresIn = tick !== null ? rec.expires_tick - tick : null
  const submitting = rec.status === 'SUBMITTING' || pending
  const tph = world.ticksPerHour

  return (
    <Card className="relative overflow-hidden">
      <div className={cn('absolute inset-y-0 left-0 w-1', toneFill[riskTone(rec.risk_level_before)])} aria-hidden />
      <div className="flex flex-col gap-3 py-3 pr-4 pl-5">
        {/* header */}
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h3 className="text-[15px] font-semibold">
                {rec.station_name} · <span className="tracking-wide">{rec.fuel}</span>
              </h3>
              {rec.uses_backup_route ? (
                <Badge tone="warn" size="sm">
                  <RouteIcon />
                  Backup route
                </Badge>
              ) : null}
              {rec.fallback ? (
                <Badge tone="warn" size="sm">
                  <FlaskConical />
                  Fallback forecast
                </Badge>
              ) : null}
              {rec.reason_source === 'llm' ? (
                <Badge tone="info" size="sm" title="Explanation written by an LLM from the computed numbers">
                  <Sparkles />
                  LLM
                </Badge>
              ) : null}
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {rec.depot_name} → {rec.station_name} · {rec.transit_ticks} ticks ({fmtTickSpan(rec.transit_ticks, world.tickMinutes)})
              transit · <span className="font-mono">{rec.id}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="tnum text-xl font-bold leading-tight">{fmtLiters(rec.quantity)}</div>
            <div
              className={cn(
                'inline-flex items-center gap-1 text-[11px]',
                expiresIn !== null && expiresIn <= 1 ? 'text-warn-ink' : 'text-muted-foreground',
              )}
            >
              <Hourglass className="size-3" aria-hidden />
              {expiresIn === null ? `expires at tick ${rec.expires_tick}` : expiresIn > 0 ? `expires in ${expiresIn} tick${expiresIn === 1 ? '' : 's'}` : 'expiring'}
            </div>
          </div>
        </div>

        {/* reason */}
        <p className="text-sm leading-snug">{rec.reason}</p>

        {/* numbers */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          <BeforeAfter
            label="Risk"
            before={<RiskChip level={rec.risk_level_before} score={rec.risk_before} />}
            after={<RiskChip level={rec.risk_level_after} score={rec.risk_after} />}
          />
          <BeforeAfter
            label="Hours to stockout"
            before={
              <span className="tnum text-sm font-semibold">
                {fmtHours(ticksToHours(rec.ticks_to_stockout_before, tph), world.horizonHours)}
              </span>
            }
            after={
              <span className="tnum text-sm font-semibold">
                {fmtHours(ticksToHours(rec.ticks_to_stockout_after, tph), world.horizonHours)}
              </span>
            }
          />
          <div className="flex flex-col gap-1">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Confidence</span>
            <span className="tnum text-sm font-semibold">{fmtPct(rec.confidence)}</span>
          </div>
        </div>

        <WhatIfChart rec={rec} capacity={capacity} tickMinutes={world.tickMinutes} />

        {/* caps, alternative, auto hint */}
        <div className="flex flex-col gap-1 text-xs">
          {rec.caps.length > 0 ? (
            <div className="text-muted-foreground">
              <span className="font-medium">Limited by:</span> {rec.caps.join(' · ')}
            </div>
          ) : null}
          {rec.alternative ? (
            <div className="text-muted-foreground">
              <span className="font-medium">Alternative:</span> {rec.alternative.description}
            </div>
          ) : null}
          <div className={cn('inline-flex items-center gap-1', rec.auto_eligible ? 'text-info-ink' : 'text-muted-foreground')}>
            <Bot className="size-3.5" aria-hidden />
            {rec.auto_eligible ? 'Auto-eligible: hybrid mode would submit this on its own.' : 'Needs an operator in hybrid mode.'}
          </div>
        </div>

        {/* actions */}
        <div className="flex flex-col gap-2 border-t pt-3">
          {rejecting ? (
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                onReject(note.trim())
                setRejecting(false)
              }}
            >
              <Input
                autoFocus
                placeholder="Optional note (why reject?)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                className="h-8 flex-1 min-w-48"
                maxLength={300}
              />
              <Button type="submit" variant="destructive" size="sm" disabled={submitting}>
                <X /> Confirm reject
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setRejecting(false)}>
                Cancel
              </Button>
            </form>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="success" size="sm" onClick={onApprove} disabled={submitting}>
                {submitting ? <LoaderCircle className="animate-spin" /> : <Check />}
                {submitting ? 'Submitting…' : 'Approve'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setRejecting(true)} disabled={submitting}>
                <X /> Reject
              </Button>
            </div>
          )}
          {outcome ? <OutcomeNote outcome={outcome} /> : null}
        </div>
      </div>
    </Card>
  )
}
