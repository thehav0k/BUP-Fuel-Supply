import { CloudOff } from 'lucide-react'
import { useStateQuery } from '@/api/queries'
import { EmptyState, WaitingForSync } from '@/components/EmptyState'
import { AlertList } from '@/components/network/AlertList'
import { DepotCard } from '@/components/network/DepotCard'
import { NetworkMap } from '@/components/network/NetworkMap'
import { RouteList } from '@/components/network/RouteList'
import { StationCard } from '@/components/network/StationCard'
import { StationDrawer } from '@/components/network/StationDrawer'
import { navigate } from '@/lib/router'
import { useWorld } from '@/lib/world'

export function NetworkScreen({ selectedStation }: { selectedStation: string | null }) {
  const { data: s, isError, isPending } = useStateQuery()
  const world = useWorld()

  if (!s) {
    return isError && !isPending ? (
      <EmptyState icon={CloudOff} title="Can't reach the backend yet">
        Polling /api/state every 2 s. The console fills in as soon as the backend answers.
      </EmptyState>
    ) : (
      <WaitingForSync />
    )
  }
  if (s.tick === null || s.stations.length === 0) return <WaitingForSync />

  const open = (id: string) => navigate('network', id)
  const close = () => navigate('network')
  const selected = s.stations.find((st) => st.id === selectedStation)

  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Stations" className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
        {s.stations.map((st) => (
          <StationCard key={st.id} station={st} world={world} onOpen={open} selected={st.id === selectedStation} />
        ))}
      </section>

      <section aria-label="Depots and map" className="grid items-start gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {s.depots.map((d) => (
          <DepotCard key={d.id} depot={d} world={world} />
        ))}
        <div className="lg:col-span-2 2xl:col-span-1">
          <NetworkMap stations={s.stations} depots={s.depots} routes={s.routes} world={world} onOpenStation={open} />
        </div>
      </section>

      <section aria-label="Routes and alerts" className="grid gap-3 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <RouteList routes={s.routes} world={world} />
        </div>
        <AlertList alerts={s.alerts} />
      </section>

      <StationDrawer
        key={selectedStation ?? 'none'}
        station={selected}
        stationId={selectedStation}
        world={world}
        onClose={close}
      />
    </div>
  )
}
