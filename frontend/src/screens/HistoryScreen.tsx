import { useAllocationsQuery, useDecisionsQuery, useEventsQuery } from '@/api/queries'
import { WaitingForSync } from '@/components/EmptyState'
import { AllocationTable } from '@/components/history/AllocationTable'
import { DecisionTable } from '@/components/history/DecisionTable'
import { EventsPanel } from '@/components/history/EventsPanel'
import { useWorld } from '@/lib/world'

export function HistoryScreen() {
  const decisions = useDecisionsQuery()
  const allocations = useAllocationsQuery()
  const events = useEventsQuery()
  const world = useWorld()

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Crisis events">
        <h2 className="mb-2 text-sm font-semibold">Crisis events</h2>
        {events.data ? (
          <EventsPanel items={events.data.items} tick={events.data.tick ?? world.tick} />
        ) : (
          <WaitingForSync detail="Loading events from the backend…" />
        )}
      </section>
      {decisions.data ? <DecisionTable items={decisions.data.items} world={world} /> : <WaitingForSync detail="Loading the decision log…" />}
      {allocations.data ? (
        <AllocationTable items={allocations.data.items} world={world} />
      ) : (
        <WaitingForSync detail="Loading allocations…" />
      )}
    </div>
  )
}
