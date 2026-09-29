import { useMutationState } from '@tanstack/react-query'
import { CircleCheck, CloudOff, X } from 'lucide-react'
import { useState } from 'react'
import { useRecommendationAction, useRecommendationsQuery, useStateQuery, type RecAction } from '@/api/queries'
import type { Recommendation } from '@/api/types'
import { EmptyState, WaitingForSync } from '@/components/EmptyState'
import { ModePanel } from '@/components/recommendations/ModePanel'
import { outcomeFromError, outcomeFromResult, type ActionOutcome } from '@/components/recommendations/outcome'
import { RecentRecommendations } from '@/components/recommendations/RecentRecommendations'
import { OutcomeNote, RecommendationCard } from '@/components/recommendations/RecommendationCard'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { fmtLiters } from '@/lib/format'
import { useWorld } from '@/lib/world'

const OPEN_STATUSES = new Set(['OPEN', 'SUBMITTING'])

export function RecommendationsScreen() {
  const openQ = useRecommendationsQuery('open')
  const allQ = useRecommendationsQuery('all')
  const { data: state } = useStateQuery()
  const world = useWorld()
  const action = useRecommendationAction()
  const [outcomes, setOutcomes] = useState<Record<string, ActionOutcome>>({})

  const pendingIds = useMutationState({
    filters: { mutationKey: ['rec-action'], status: 'pending' },
    select: (m) => (m.state.variables as RecAction | undefined)?.id,
  })

  const run = (rec: Recommendation, act: 'approve' | 'reject', note?: string) => {
    action
      .mutateAsync({ id: rec.id, action: act, note })
      .then((res) => setOutcomes((o) => ({ ...o, [rec.id]: outcomeFromResult(rec.id, act, res, note) })))
      .catch((err: unknown) => setOutcomes((o) => ({ ...o, [rec.id]: outcomeFromError(rec.id, act, err, rec) })))
  }
  const dismiss = (id: string) =>
    setOutcomes((o) => {
      const next = { ...o }
      delete next[id]
      return next
    })

  const capacityOf = (stationId: string, fuel: string) =>
    state?.stations.find((s) => s.id === stationId)?.fuels.find((f) => f.fuel === fuel)?.capacity ?? null

  const openItems = openQ.data?.items ?? []
  const openIds = new Set(openItems.map((r) => r.id))
  // Outcomes whose card already left the open list stay visible here until dismissed.
  const handled = Object.values(outcomes).filter((o) => !openIds.has(o.id))
  const recent = (allQ.data?.items ?? [])
    .filter((r) => !OPEN_STATUSES.has(r.status))
    .sort((a, b) => b.created_tick - a.created_tick || b.id.localeCompare(a.id, undefined, { numeric: true }))
    .slice(0, 20)
  const tick = openQ.data?.tick ?? state?.tick ?? null

  return (
    <div className="flex flex-col gap-4">
      <ModePanel />

      {handled.length > 0 ? (
        <section aria-label="Just handled" className="flex flex-col gap-2">
          {handled.map((o) => (
            <Card key={o.id} className="flex items-start gap-3 px-4 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="mb-1 text-xs text-muted-foreground">
                  {o.action === 'approve' ? 'Approved' : 'Rejected'}{' '}
                  <span className="font-mono">{o.id}</span>
                  {o.rec ? ` · ${o.rec.station_name} · ${o.rec.fuel} · ${fmtLiters(o.rec.quantity)}` : ''}
                </div>
                <OutcomeNote outcome={o} />
              </div>
              <Button variant="ghost" size="icon" aria-label="Dismiss" onClick={() => dismiss(o.id)}>
                <X />
              </Button>
            </Card>
          ))}
        </section>
      ) : null}

      <section aria-label="Open recommendations">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">
            Open recommendations <span className="tnum text-muted-foreground">({openItems.length})</span>
          </h2>
          <span className="text-xs text-muted-foreground">highest risk first</span>
        </div>
        {!openQ.data ? (
          openQ.isError ? (
            <EmptyState icon={CloudOff} title="Can't load recommendations">
              Retrying every 2 s.
            </EmptyState>
          ) : (
            <WaitingForSync />
          )
        ) : openItems.length === 0 ? (
          <EmptyState icon={CircleCheck} title="No open recommendations">
            {state?.tick === null
              ? 'Waiting for the first sync with the simulator.'
              : 'Every station-fuel pair is covered. New recommendations appear here as risk rises.'}
          </EmptyState>
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {openItems.map((rec) => (
              <RecommendationCard
                key={rec.id}
                rec={rec}
                world={world}
                tick={tick}
                capacity={capacityOf(rec.station_id, rec.fuel)}
                pending={pendingIds.includes(rec.id)}
                outcome={outcomes[rec.id]}
                onApprove={() => run(rec, 'approve')}
                onReject={(note) => run(rec, 'reject', note || undefined)}
              />
            ))}
          </div>
        )}
      </section>

      <RecentRecommendations items={recent} world={world} />
    </div>
  )
}
