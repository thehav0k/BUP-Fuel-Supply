import type { DepotView, RouteView, StationView } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { riskTone, toneColor, worstRisk } from '@/lib/tone'
import type { World } from '@/lib/world'

/**
 * PRD 9.6: schematic map of the two regions. Positions are hand-placed for the
 * fixed world; unknown ids fall back to an automatic spot inside their region.
 */
const W = 520
const H = 330

interface Box {
  x: number
  y: number
  w: number
  h: number
}

const REGION_BOX: Record<string, Box & { labelBottom?: boolean }> = {
  dhaka: { x: 10, y: 10, w: 250, h: 205 },
  chattogram: { x: 262, y: 115, w: 248, h: 205, labelBottom: true },
}

const KNOWN_POS: Record<string, [number, number]> = {
  gazipur: [78, 72],
  tongi: [196, 70],
  mirpur: [150, 170],
  karnaphuli: [340, 180],
  patiya: [428, 214],
  coxsbazar: [456, 286],
}

/** Backup (cross-region) routes bow away from the primaries so lines never overlap. */
const CURVE: Record<string, [number, number]> = {
  'gazipur-karnaphuli': [250, 90],
  'patiya-mirpur': [270, 262],
}

const bare = (id: string) => id.replace(/^(station|depot|region|route)-/, '')

function regionKey(regionId: string, i: number): string {
  const b = bare(regionId)
  if (REGION_BOX[b]) return b
  return i % 2 === 0 ? 'dhaka' : 'chattogram'
}

function layout(stations: StationView[], depots: DepotView[]) {
  const pos = new Map<string, [number, number]>()
  const fallbackCount = new Map<string, number>()
  const place = (id: string, regionId: string, i: number) => {
    const k = bare(id)
    if (KNOWN_POS[k]) {
      pos.set(id, KNOWN_POS[k])
      return
    }
    const rk = regionKey(regionId, i)
    const box = REGION_BOX[rk]
    const n = fallbackCount.get(rk) ?? 0
    fallbackCount.set(rk, n + 1)
    pos.set(id, [box.x + 40 + ((n * 70) % (box.w - 60)), box.y + 60 + Math.floor((n * 70) / (box.w - 60)) * 60])
  }
  depots.forEach((d, i) => place(d.id, d.region_id, i))
  stations.forEach((s, i) => place(s.id, s.region_id, i))
  return pos
}

function routeStyle(r: RouteView, tick: number | null) {
  const scheduled =
    r.scheduled_disruption && tick !== null && r.scheduled_disruption.start_tick > tick ? r.scheduled_disruption : null
  if (r.status === 'DISRUPTED') {
    return { stroke: 'var(--crit)', width: 2.5, dash: '7 5', label: 'disrupted' }
  }
  if (scheduled) {
    return { stroke: 'var(--warn)', width: r.is_backup ? 1.75 : 2.5, dash: r.is_backup ? '2 4' : undefined, label: 'disruption scheduled' }
  }
  if (r.is_backup) return { stroke: 'var(--chart-axis)', width: 1.5, dash: '2 4', label: 'backup, available' }
  return { stroke: 'var(--ok)', width: 2.5, dash: undefined, label: 'available' }
}

export function NetworkMap({
  stations,
  depots,
  routes,
  world,
  onOpenStation,
}: {
  stations: StationView[]
  depots: DepotView[]
  routes: RouteView[]
  world: World
  onOpenStation: (id: string) => void
}) {
  const pos = layout(stations, depots)
  const regionIds = world.regionIds.length ? world.regionIds : ['region-dhaka', 'region-chattogram']

  return (
    <Card>
      <CardHeader>
        <CardTitle>Network map</CardTitle>
      </CardHeader>
      <CardContent className="pb-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Network map of depots, stations and routes">
          {regionIds.map((rid, i) => {
            const box = REGION_BOX[regionKey(rid, i)]
            return (
              <g key={rid}>
                <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={18} fill="var(--muted)" stroke="var(--border)" />
                <text x={box.x + 14} y={box.labelBottom ? box.y + box.h - 12 : box.y + 22} fontSize={12} fontWeight={600} fill="var(--muted-foreground)">
                  {world.regionName(rid)}
                </text>
              </g>
            )
          })}

          {routes.map((r) => {
            const a = pos.get(r.source_depot_id)
            const b = pos.get(r.destination_station_id)
            if (!a || !b) return null
            const st = routeStyle(r, world.tick)
            const c = CURVE[bare(r.id)]
            const d = c ? `M${a[0]},${a[1]} Q${c[0]},${c[1]} ${b[0]},${b[1]}` : `M${a[0]},${a[1]} L${b[0]},${b[1]}`
            return (
              <path key={r.id} d={d} fill="none" stroke={st.stroke} strokeWidth={st.width} strokeDasharray={st.dash} strokeLinecap="round">
                <title>
                  {world.routeLabel(r.id)}: {r.status}
                  {r.is_backup ? ' (backup)' : ''}, {st.label}, {r.transit_ticks} ticks
                </title>
              </path>
            )
          })}

          {depots.map((d) => {
            const p = pos.get(d.id)
            if (!p) return null
            return (
              <g key={d.id}>
                <rect
                  x={p[0] - 11}
                  y={p[1] - 11}
                  width={22}
                  height={22}
                  rx={5}
                  fill={d.status === 'OPEN' ? 'var(--foreground)' : 'var(--warn)'}
                  stroke="var(--card)"
                  strokeWidth={2}
                />
                <text x={p[0]} y={p[1] + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="var(--card)">
                  D
                </text>
                <text x={p[0]} y={p[1] + 26} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--foreground)">
                  {d.name}
                </text>
                <title>
                  {d.name} depot ({d.status})
                </title>
              </g>
            )
          })}

          {stations.map((s) => {
            const p = pos.get(s.id)
            if (!p) return null
            const worst = worstRisk(s.fuels.map((f) => f.risk_level))
            const outage = s.status === 'OUTAGE'
            return (
              <g
                key={s.id}
                role="button"
                tabIndex={0}
                className="cursor-pointer outline-none"
                onClick={() => onOpenStation(s.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') onOpenStation(s.id)
                }}
              >
                <circle cx={p[0]} cy={p[1]} r={20} fill="transparent" />
                <circle cx={p[0]} cy={p[1]} r={11} fill={toneColor[riskTone(worst)]} stroke="var(--card)" strokeWidth={2} />
                {outage ? (
                  <circle cx={p[0]} cy={p[1]} r={16} fill="none" stroke="var(--crit)" strokeWidth={2} strokeDasharray="3 3" />
                ) : null}
                <text x={p[0]} y={p[1] + 28} textAnchor="middle" fontSize={11} fontWeight={600} fill="var(--foreground)">
                  {s.name}
                </text>
                {outage ? (
                  <text x={p[0]} y={p[1] - 20} textAnchor="middle" fontSize={10} fontWeight={700} fill="var(--crit)">
                    OUTAGE
                  </text>
                ) : null}
                <title>
                  {s.name}: worst risk {worst ?? 'n/a'}
                  {outage ? ' (OUTAGE)' : ''}. Click for forecast.
                </title>
              </g>
            )
          })}
        </svg>
        <MapLegend />
      </CardContent>
    </Card>
  )
}

function MapLegend() {
  const line = (stroke: string, dash?: string, width = 2.5) => (
    <svg width="22" height="6" aria-hidden>
      <line x1="1" y1="3" x2="21" y2="3" stroke={stroke} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" />
    </svg>
  )
  const dot = (fill: string) => (
    <svg width="10" height="10" aria-hidden>
      <circle cx="5" cy="5" r="4.5" fill={fill} />
    </svg>
  )
  return (
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1">{line('var(--ok)')}available</span>
      <span className="inline-flex items-center gap-1">{line('var(--chart-axis)', '2 4', 1.5)}backup</span>
      <span className="inline-flex items-center gap-1">{line('var(--warn)')}disruption scheduled</span>
      <span className="inline-flex items-center gap-1">{line('var(--crit)', '7 5')}disrupted</span>
      <span className="inline-flex items-center gap-1">
        {dot('var(--ok)')}
        {dot('var(--warn)')}
        {dot('var(--crit)')} station worst risk
      </span>
    </div>
  )
}
