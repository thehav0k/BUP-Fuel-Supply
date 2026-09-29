import { useMemo } from 'react'
import { useStateQuery } from '@/api/queries'
import type { Fuel, State } from '@/api/types'

export const FUELS: Fuel[] = ['DIESEL', 'PETROL', 'OCTANE']

/** Forecast/stockout horizon used by the backend (ticks). */
export const HORIZON_TICKS = 48

const KNOWN_NAMES: Record<string, string> = {
  mirpur: 'Mirpur',
  tongi: 'Tongi',
  karnaphuli: 'Karnaphuli',
  coxsbazar: "Cox's Bazar",
  gazipur: 'Gazipur',
  patiya: 'Patiya',
  dhaka: 'Dhaka',
  chattogram: 'Chattogram',
}

/** "station-coxsbazar" -> "Cox's Bazar", "region-dhaka" -> "Dhaka" */
export function prettyId(id: string | null | undefined): string {
  if (!id) return '—'
  const bare = id.replace(/^(station|depot|region|route)-/, '')
  if (KNOWN_NAMES[bare]) return KNOWN_NAMES[bare]
  return bare
    .split(/[-_]/)
    .map((w) => (KNOWN_NAMES[w] ? KNOWN_NAMES[w] : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

export interface World {
  tick: number | null
  ticksPerHour: number
  tickMinutes: number
  horizonHours: number
  stationName: (id: string | null | undefined) => string
  depotName: (id: string | null | undefined) => string
  regionName: (id: string | null | undefined) => string
  routeLabel: (id: string | null | undefined) => string
  stationIds: string[]
  depotIds: string[]
  routeIds: string[]
  regionIds: string[]
}

export function buildWorld(state: State | undefined): World {
  const stationNames = new Map(state?.stations.map((s) => [s.id, s.name]) ?? [])
  const depotNames = new Map(state?.depots.map((d) => [d.id, d.name]) ?? [])
  const routes = new Map(state?.routes.map((r) => [r.id, r]) ?? [])
  const ticksPerHour = state?.ticks_per_hour || 4
  const tickMinutes = state?.tick_minutes || 15

  const stationName = (id: string | null | undefined) => (id && stationNames.get(id)) || prettyId(id)
  const depotName = (id: string | null | undefined) => (id && depotNames.get(id)) || prettyId(id)
  const routeLabel = (id: string | null | undefined) => {
    if (!id) return '—'
    const r = routes.get(id)
    if (r) return `${depotName(r.source_depot_id)} → ${stationName(r.destination_station_id)}`
    const parts = id.replace(/^route-/, '').split('-')
    return parts.length === 2 ? `${prettyId(parts[0])} → ${prettyId(parts[1])}` : prettyId(id)
  }

  const regionIds = Array.from(
    new Set([...(state?.stations.map((s) => s.region_id) ?? []), ...(state?.depots.map((d) => d.region_id) ?? [])]),
  )

  return {
    tick: state?.tick ?? null,
    ticksPerHour,
    tickMinutes,
    horizonHours: HORIZON_TICKS / ticksPerHour,
    stationName,
    depotName,
    regionName: prettyId,
    routeLabel,
    stationIds: state?.stations.map((s) => s.id) ?? [],
    depotIds: state?.depots.map((d) => d.id) ?? [],
    routeIds: state?.routes.map((r) => r.id) ?? [],
    regionIds,
  }
}

/** Name lookups and time units derived from the latest /api/state. */
export function useWorld(): World {
  const { data } = useStateQuery()
  return useMemo(() => buildWorld(data), [data])
}
