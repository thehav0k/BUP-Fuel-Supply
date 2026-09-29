import type { DepotView, RouteView, StationView } from '@/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { DETAIL, OVERVIEW, project, type MapView } from '@/lib/bangladeshMap'
import { riskTone, toneColor, worstRisk } from '@/lib/tone'
import type { World } from '@/lib/world'

/**
 * PRD 9.6: the network on a real map of Bangladesh (division boundaries from geoBoundaries, CC BY 4.0).
 * Left: the whole country with the operating corridor boxed. Right: the corridor zoomed in, with depots,
 * stations and routes at their real coordinates. Sites closer than a marker's width are fanned out a little
 * and tied back to their true location with a leader line, so nothing overlaps.
 */
const VIEW_W = 780
const VIEW_H = 562

type Site = { lon: number; lat: number; dx: number; dy: number; label: 'above' | 'below' | 'right' | 'left' }

/** Real coordinates; dx/dy = display offset (px) in the detail view for the clustered sites. */
const SITES: Record<string, Site> = {
  'depot-gazipur': { lon: 90.4203, lat: 23.9999, dx: 22, dy: -36, label: 'above' },
  'station-tongi': { lon: 90.4023, lat: 23.8915, dx: 74, dy: 2, label: 'right' },
  'station-mirpur': { lon: 90.3654, lat: 23.8223, dx: -18, dy: 44, label: 'below' },
  'depot-patiya': { lon: 91.979, lat: 22.2953, dx: 40, dy: -10, label: 'right' },
  'station-karnaphuli': { lon: 91.8436, lat: 22.3246, dx: -42, dy: -56, label: 'left' },
  'station-coxsbazar': { lon: 92.0058, lat: 21.4272, dx: 0, dy: 0, label: 'left' },
}

/** Cross-region backup routes bow away from the primaries (quadratic control points, detail view px). */
const BOW: Record<string, [number, number]> = {
  'route-gazipur-karnaphuli': [700, 60],
  'route-patiya-mirpur': [430, 480],
}

const REGION_OF: Record<string, string> = { Dhaka: 'region-dhaka', Chattogram: 'region-chattogram' }

function truePos(v: MapView, id: string): [number, number] | null {
  const s = SITES[id]
  return s ? project(v, s.lon, s.lat) : null
}

function shownPos(id: string): [number, number] | null {
  const p = truePos(DETAIL, id)
  const s = SITES[id]
  return p && s ? [p[0] + s.dx, p[1] + s.dy] : null
}

function routeStyle(r: RouteView, tick: number | null) {
  const scheduled =
    r.scheduled_disruption && tick !== null && r.scheduled_disruption.start_tick > tick ? r.scheduled_disruption : null
  if (r.status === 'DISRUPTED') return { stroke: 'var(--crit)', width: 2.5, dash: '7 5', label: 'disrupted' }
  if (scheduled) return { stroke: 'var(--warn)', width: 2.5, dash: r.is_backup ? '3 4' : undefined, label: 'disruption scheduled' }
  if (r.is_backup) return { stroke: 'var(--chart-axis)', width: 1.5, dash: '3 4', label: 'backup, available' }
  return { stroke: 'var(--ok)', width: 3, dash: undefined, label: 'available' }
}

function labelAnchor(site: Site | undefined, p: [number, number], gap: number) {
  switch (site?.label) {
    case 'above':
      return { x: p[0], y: p[1] - gap - 14, anchor: 'middle' as const }
    case 'right':
      return { x: p[0] + gap, y: p[1] - 2, anchor: 'start' as const }
    case 'left':
      return { x: p[0] - gap, y: p[1] - 2, anchor: 'end' as const }
    default:
      return { x: p[0], y: p[1] + gap + 10, anchor: 'middle' as const }
  }
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
  const spikeRegions = new Set(stations.filter((s) => s.spike).map((s) => s.region_id))
  const regionFill = (division: string) => {
    const rid = REGION_OF[division]
    if (!rid) return { fill: 'var(--muted)', opacity: 1 }
    return { fill: spikeRegions.has(rid) ? 'var(--warn)' : 'var(--primary)', opacity: 0.14 }
  }
  const [c0, c1] = [project(OVERVIEW, 89.75, 24.45), project(OVERVIEW, 92.45, 21.15)]
  const kmPx = (50 / 111.32) * DETAIL.k

  return (
    <Card>
      <CardHeader>
        <CardTitle>Network map · Bangladesh</CardTitle>
      </CardHeader>
      <CardContent className="pb-3">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="mx-auto h-auto w-full max-w-[880px]"
          role="img"
          aria-label="Map of Bangladesh with fuel depots, stations and routes"
        >
          <defs>
            <clipPath id="detail-clip">
              <rect x={DETAIL.x} y={DETAIL.y} width={DETAIL.width} height={DETAIL.height} rx={10} />
            </clipPath>
          </defs>

          {/* ---------- overview: the whole country ---------- */}
          <text x={OVERVIEW.x} y={26} fontSize={13} fontWeight={600} fill="var(--foreground)">
            Bangladesh
          </text>
          <text x={OVERVIEW.x} y={40} fontSize={10.5} fill="var(--muted-foreground)">
            8 divisions · operating corridor boxed
          </text>
          {OVERVIEW.divisions.map((dv) => {
            const f = regionFill(dv.name)
            return (
              <g key={`o-${dv.name}`}>
                <path d={dv.d} fill="var(--muted)" stroke="var(--border)" strokeWidth={0.8} />
                {REGION_OF[dv.name] ? <path d={dv.d} fill={f.fill} fillOpacity={f.opacity} /> : null}
              </g>
            )
          })}
          <rect
            x={c0[0]}
            y={c0[1]}
            width={c1[0] - c0[0]}
            height={c1[1] - c0[1]}
            fill="none"
            stroke="var(--foreground)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
          <path
            d={`M${c1[0]} ${c0[1] + 8} L${DETAIL.x - 6} ${DETAIL.y + 40}`}
            stroke="var(--chart-axis)"
            strokeWidth={0.8}
            strokeDasharray="2 3"
            fill="none"
          />
          {Object.keys(SITES).map((id) => {
            const p = truePos(OVERVIEW, id)
            return p ? <circle key={`op-${id}`} cx={p[0]} cy={p[1]} r={2.4} fill="var(--foreground)" /> : null
          })}
          {[
            ['Dhaka', 90.25, 23.2],
            ['Chattogram', 91.95, 22.55],
            ['Sylhet', 91.6, 24.6],
            ['Rajshahi', 88.8, 24.5],
            ['Rangpur', 89.15, 25.8],
            ['Khulna', 89.2, 22.95],
            ['Barishal', 90.3, 22.45],
            ['Mymensingh', 90.4, 24.9],
          ].map(([name, lon, lat]) => {
            const [x, y] = project(OVERVIEW, lon as number, lat as number)
            const key = REGION_OF[name as string]
            return (
              <text
                key={`ol-${name}`}
                x={x}
                y={y}
                textAnchor="middle"
                fontSize={key ? 10 : 9}
                fontWeight={key ? 600 : 400}
                fill={key ? 'var(--foreground)' : 'var(--muted-foreground)'}
              >
                {name}
              </text>
            )
          })}
          <text
            x={project(OVERVIEW, 88.7, 20.85)[0]}
            y={project(OVERVIEW, 88.7, 20.85)[1]}
            fontSize={10}
            fontStyle="italic"
            fill="var(--muted-foreground)"
          >
            Bay of Bengal
          </text>
          <text x={OVERVIEW.x} y={VIEW_H - 8} fontSize={9} fill="var(--muted-foreground)">
            Boundaries: geoBoundaries (CC BY 4.0)
          </text>

          {/* ---------- detail: the Dhaka–Chattogram corridor ---------- */}
          <rect
            x={DETAIL.x}
            y={DETAIL.y}
            width={DETAIL.width}
            height={DETAIL.height}
            rx={10}
            fill="var(--primary)"
            fillOpacity={0.12}
            stroke="var(--border)"
          />
          <g clipPath="url(#detail-clip)">
            {DETAIL.divisions.map((dv) => {
              const f = regionFill(dv.name)
              return (
                <g key={`d-${dv.name}`}>
                  <path d={dv.d} fill="var(--muted)" stroke="var(--border)" strokeWidth={1} />
                  {REGION_OF[dv.name] ? <path d={dv.d} fill={f.fill} fillOpacity={f.opacity} /> : null}
                </g>
              )
            })}
            <text x={DETAIL.x + 10} y={project(DETAIL, 90, 22.95)[1]} fontSize={10.5} fontWeight={700}
              letterSpacing={1} fill="var(--muted-foreground)">
              <tspan x={DETAIL.x + 10}>DHAKA</tspan>
              <tspan x={DETAIL.x + 10} dy={13}>DIVISION</tspan>
            </text>
            <text x={project(DETAIL, 91.98, 23.05)[0]} y={project(DETAIL, 91.98, 23.05)[1]} textAnchor="middle"
              fontSize={10.5} fontWeight={700} letterSpacing={1} fill="var(--muted-foreground)">
              <tspan x={project(DETAIL, 91.98, 23.05)[0]}>CHATTOGRAM</tspan>
              <tspan x={project(DETAIL, 91.98, 23.05)[0]} dy={13}>DIVISION</tspan>
            </text>
            <text x={project(DETAIL, 90.15, 21.55)[0]} y={project(DETAIL, 90.15, 21.55)[1]} fontSize={11}
              fontStyle="italic" fill="var(--muted-foreground)">
              Bay of Bengal
            </text>
          </g>

          {/* north arrow and 50 km scale bar */}
          <g aria-hidden>
            <path d={`M${DETAIL.x + DETAIL.width - 22} ${DETAIL.y + 34} l6 -16 l6 16 l-6 -5 z`} fill="var(--foreground)" />
            <text x={DETAIL.x + DETAIL.width - 16} y={DETAIL.y + 48} textAnchor="middle" fontSize={10} fill="var(--foreground)">
              N
            </text>
            <line x1={DETAIL.x + 14} x2={DETAIL.x + 14 + kmPx} y1={DETAIL.y + DETAIL.height - 16}
              y2={DETAIL.y + DETAIL.height - 16} stroke="var(--foreground)" strokeWidth={2} />
            <text x={DETAIL.x + 14} y={DETAIL.y + DETAIL.height - 22} fontSize={10} fill="var(--foreground)">
              50 km
            </text>
          </g>

          {/* leader lines: display marker -> true location */}
          {Object.keys(SITES).map((id) => {
            const t = truePos(DETAIL, id)
            const s = shownPos(id)
            if (!t || !s || Math.hypot(t[0] - s[0], t[1] - s[1]) < 6) return null
            return (
              <g key={`lead-${id}`} aria-hidden>
                <line x1={t[0]} y1={t[1]} x2={s[0]} y2={s[1]} stroke="var(--chart-axis)" strokeWidth={0.8} strokeDasharray="2 2" />
                <circle cx={t[0]} cy={t[1]} r={2.2} fill="var(--foreground)" />
              </g>
            )
          })}

          {routes.map((r) => {
            const a = shownPos(r.source_depot_id)
            const b = shownPos(r.destination_station_id)
            if (!a || !b) return null
            const st = routeStyle(r, world.tick)
            const bow = BOW[r.id]
            const d = bow ? `M${a[0]},${a[1]} Q${bow[0]},${bow[1]} ${b[0]},${b[1]}` : `M${a[0]},${a[1]} L${b[0]},${b[1]}`
            const mid: [number, number] = bow
              ? [0.25 * a[0] + 0.5 * bow[0] + 0.25 * b[0], 0.25 * a[1] + 0.5 * bow[1] + 0.25 * b[1]]
              : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
            return (
              <g key={r.id}>
                <path d={d} fill="none" stroke={st.stroke} strokeWidth={st.width} strokeDasharray={st.dash} strokeLinecap="round">
                  <title>
                    {world.routeLabel(r.id)}: {st.label}
                    {r.is_backup ? ' (cross-region backup)' : ''} · {r.transit_ticks} ticks · max {r.max_shipment.toLocaleString()} L
                  </title>
                </path>
                {r.status === 'DISRUPTED' ? (
                  <g>
                    <circle cx={mid[0]} cy={mid[1]} r={8} fill="var(--card)" stroke="var(--crit)" strokeWidth={1.5} />
                    <path d={`M${mid[0] - 3.5} ${mid[1] - 3.5}l7 7M${mid[0] + 3.5} ${mid[1] - 3.5}l-7 7`} stroke="var(--crit)" strokeWidth={1.8} />
                  </g>
                ) : null}
              </g>
            )
          })}

          {depots.map((d) => {
            const p = shownPos(d.id)
            if (!p) return null
            const fill = d.fuels.length ? d.fuels.reduce((acc, f) => acc + f.fill_pct, 0) / d.fuels.length : 0
            const lab = labelAnchor(SITES[d.id], p, 14)
            return (
              <g key={d.id}>
                <rect x={p[0] - 11} y={p[1] - 11} width={22} height={22} rx={5}
                  fill={d.status === 'OPEN' ? 'var(--foreground)' : 'var(--warn)'} stroke="var(--card)" strokeWidth={2} />
                <text x={p[0]} y={p[1] + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="var(--card)">
                  D
                </text>
                <text x={lab.x} y={lab.y} textAnchor={lab.anchor} fontSize={11.5} fontWeight={600} fill="var(--foreground)">
                  {d.name}
                </text>
                <text x={lab.x} y={lab.y + 13} textAnchor={lab.anchor} fontSize={10} fill="var(--muted-foreground)">
                  stock {fill.toFixed(0)}%{d.status !== 'OPEN' ? ` · ${d.status.toLowerCase()}` : ''}
                </text>
                <title>
                  {d.name} ({d.status}): average stock {fill.toFixed(0)}% of capacity
                </title>
              </g>
            )
          })}

          {stations.map((s) => {
            const p = shownPos(s.id)
            if (!p) return null
            const worst = worstRisk(s.fuels.map((f) => f.risk_level))
            const outage = s.status === 'OUTAGE'
            const hours = s.fuels.map((f) => f.hours_to_stockout).filter((h): h is number => h !== null)
            const soonest = hours.length ? Math.min(...hours) : null
            const lab = labelAnchor(SITES[s.id], p, 16)
            const spike = s.demand_multiplier > 1.001
            const leftBadge = SITES[s.id]?.label === 'right'
            const badgeX = leftBadge ? p[0] - 39 : p[0] + 7
            const badgeY = leftBadge ? p[1] + 10 : p[1] - 25
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
                {outage ? (
                  <circle cx={p[0]} cy={p[1]} r={16} fill="none" stroke="var(--crit)" strokeWidth={2} strokeDasharray="3 3" />
                ) : null}
                <circle cx={p[0]} cy={p[1]} r={11} fill={toneColor[riskTone(worst)]} stroke="var(--card)" strokeWidth={2.5} />
                {spike ? (
                  <g>
                    <rect x={badgeX} y={badgeY} width={32} height={14} rx={7} fill="var(--warn)" />
                    <text x={badgeX + 16} y={badgeY + 10} textAnchor="middle" fontSize={9.5} fontWeight={700} fill="#1a1a19">
                      ×{s.demand_multiplier.toFixed(1)}
                    </text>
                  </g>
                ) : null}
                <text x={lab.x} y={lab.y} textAnchor={lab.anchor} fontSize={11.5} fontWeight={600} fill="var(--foreground)">
                  {s.name.replace(/ (Fuel|Industrial|Highway|Regional) Station$/, '')}
                </text>
                <text x={lab.x} y={lab.y + 13} textAnchor={lab.anchor} fontSize={10}
                  fill={outage ? 'var(--crit-ink)' : 'var(--muted-foreground)'}>
                  {outage ? 'OUTAGE' : soonest === null ? 'no stockout in 12 h' : `stockout in ${soonest.toFixed(1)} h`}
                </text>
                <title>
                  {s.name}: worst risk {worst ?? 'n/a'}
                  {outage ? ' (OUTAGE)' : ''}
                  {spike ? `, demand ×${s.demand_multiplier.toFixed(2)}` : ''}. Click for the forecast.
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
      <span className="inline-flex items-center gap-1">{line('var(--ok)')}route available</span>
      <span className="inline-flex items-center gap-1">{line('var(--chart-axis)', '3 4', 1.5)}backup route</span>
      <span className="inline-flex items-center gap-1">{line('var(--warn)')}disruption scheduled</span>
      <span className="inline-flex items-center gap-1">{line('var(--crit)', '7 5')}disrupted</span>
      <span className="inline-flex items-center gap-1">
        {dot('var(--ok)')}
        {dot('var(--warn)')}
        {dot('var(--crit)')} station worst risk
      </span>
      <span className="inline-flex items-center gap-1">
        <svg width="12" height="12" aria-hidden>
          <rect x="1" y="1" width="10" height="10" rx="2.5" fill="var(--foreground)" />
        </svg>
        depot
      </span>
      <span className="inline-flex items-center gap-1">
        <svg width="10" height="10" aria-hidden>
          <circle cx="5" cy="5" r="2.2" fill="var(--foreground)" />
        </svg>
        true location
      </span>
      <span>tinted = operating divisions (amber during a demand spike)</span>
    </div>
  )
}
