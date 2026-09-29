import type { CreateEventBody, CreateFaultBody, EventType, FaultType, State } from '@/api/types'

export type ListParam = 'region_ids' | 'station_ids' | 'route_ids' | 'depot_ids' | 'fuel_types'
export type NumParam = 'multiplier' | 'delay_ticks' | 'factor'

export interface EventTypeDef {
  type: EventType
  label: string
  effect: string
  lists: ListParam[]
  nums: { key: NumParam; label: string; def: number; step: number; min: number; max?: number; integer?: boolean }[]
  defaultDuration: number
}

export const EVENT_TYPES: EventTypeDef[] = [
  {
    type: 'demand_spike',
    label: 'Demand spike',
    effect: "Multiplies the stations' demand while active.",
    lists: ['region_ids', 'station_ids'],
    nums: [{ key: 'multiplier', label: 'Multiplier', def: 1.5, step: 0.1, min: 0.1, max: 10 }],
    defaultDuration: 32,
  },
  {
    type: 'route_disruption',
    label: 'Route disruption',
    effect: 'Routes become DISRUPTED; shipments departing on them fail.',
    lists: ['route_ids'],
    nums: [],
    defaultDuration: 32,
  },
  {
    type: 'station_outage',
    label: 'Station outage',
    effect: 'Stations close (OUTAGE) and serve nothing.',
    lists: ['station_ids'],
    nums: [],
    defaultDuration: 16,
  },
  {
    type: 'depot_constraint',
    label: 'Depot constraint',
    effect: 'Depots become CONSTRAINED (still shippable).',
    lists: ['depot_ids'],
    nums: [],
    defaultDuration: 16,
  },
  {
    type: 'shipment_delay',
    label: 'Shipment delay',
    effect: 'One-shot: scheduled supply arrivals in the window slip by N ticks (DELAYED).',
    lists: ['depot_ids', 'fuel_types'],
    nums: [{ key: 'delay_ticks', label: 'Delay (ticks)', def: 2, step: 1, min: 1, max: 500, integer: true }],
    defaultDuration: 64,
  },
  {
    type: 'supply_shortfall',
    label: 'Supply shortfall',
    effect: 'One-shot: scheduled supply arrivals in the window are multiplied by the factor.',
    lists: ['depot_ids', 'fuel_types'],
    nums: [{ key: 'factor', label: 'Factor', def: 0.5, step: 0.05, min: 0, max: 1 }],
    defaultDuration: 64,
  },
]

export const LIST_LABEL: Record<ListParam, string> = {
  region_ids: 'Regions',
  station_ids: 'Stations',
  route_ids: 'Routes',
  depot_ids: 'Depots',
  fuel_types: 'Fuels',
}

export interface FaultTypeDef {
  type: FaultType
  label: string
  effect: string
  param?: { key: 'delay_ms' | 'rate'; label: string; def: number; step: number; min: number; max: number }
}

export const FAULT_TYPES: FaultTypeDef[] = [
  {
    type: 'latency',
    label: 'Latency',
    effect: 'Delays every /v1/* request.',
    param: { key: 'delay_ms', label: 'Delay (ms)', def: 500, step: 100, min: 1, max: 60000 },
  },
  { type: 'unavailable', label: 'Unavailable', effect: '503 on every /v1/* call, including the stream.' },
  {
    type: 'error_rate',
    label: 'Error rate',
    effect: 'Random 503s on /v1/* calls.',
    param: { key: 'rate', label: 'Rate (0-1)', def: 0.25, step: 0.05, min: 0, max: 1 },
  },
  { type: 'stale_data', label: 'Stale data', effect: 'Adds X-Simulator-Stale: true to /v1/* GETs.' },
  { type: 'stream_disconnect', label: 'Stream disconnect', effect: '/v1/stream returns 503; polling continues.' },
]

// ------------------------------------------------------------------ presets (PRD section 8, steps 3-8)

function findId(ids: string[], ...needles: string[]): string | undefined {
  return ids.find((id) => needles.every((n) => id.includes(n)))
}

/** Resolve the canonical demo ids from live state, falling back to the documented ids. */
export function demoIds(state: State | undefined) {
  const regionIds = [...new Set(state?.stations.map((s) => s.region_id) ?? [])]
  const depotIds = state?.depots.map((d) => d.id) ?? []
  const routeFor = (depot: string, station: string) =>
    state?.routes.find((r) => r.source_depot_id.includes(depot) && r.destination_station_id.includes(station))?.id
  return {
    dhaka: findId(regionIds, 'dhaka') ?? 'region-dhaka',
    gazipur: findId(depotIds, 'gazipur') ?? 'depot-gazipur',
    gazipurMirpur: routeFor('gazipur', 'mirpur') ?? 'route-gazipur-mirpur',
    gazipurTongi: routeFor('gazipur', 'tongi') ?? 'route-gazipur-tongi',
  }
}

export type Preset =
  | { id: string; step: number; label: string; hint: string; kind: 'event'; build: (s: State | undefined) => CreateEventBody }
  | { id: string; step: number; label: string; hint: string; kind: 'fault'; build: () => CreateFaultBody }

export const PRESETS: Preset[] = [
  {
    id: 'spike',
    step: 3,
    label: 'Dhaka demand spike ×1.8 · 32 ticks',
    hint: 'Spike badges on Mirpur and Tongi; recommendations appear.',
    kind: 'event',
    build: (s) => ({
      type: 'demand_spike',
      duration_ticks: 32,
      parameters: { multiplier: 1.8, region_ids: [demoIds(s).dhaka], station_ids: [] },
    }),
  },
  {
    id: 'disrupt-mirpur',
    step: 4,
    label: 'Disrupt Gazipur → Mirpur · 32 ticks',
    hint: 'Next Mirpur recommendation uses the Patiya backup route.',
    kind: 'event',
    build: (s) => ({ type: 'route_disruption', duration_ticks: 32, parameters: { route_ids: [demoIds(s).gazipurMirpur] } }),
  },
  {
    id: 'disrupt-tongi',
    step: 5,
    label: 'Disrupt Gazipur → Tongi · 32 ticks',
    hint: '"No route" alert: Tongi is a single point of failure.',
    kind: 'event',
    build: (s) => ({ type: 'route_disruption', duration_ticks: 32, parameters: { route_ids: [demoIds(s).gazipurTongi] } }),
  },
  {
    id: 'shortfall',
    step: 6,
    label: 'Supply shortfall Gazipur ×0.5 · 64 ticks',
    hint: 'Depot projection drops; the reserve rule limits outbound.',
    kind: 'event',
    build: (s) => ({
      type: 'supply_shortfall',
      duration_ticks: 64,
      parameters: { factor: 0.5, depot_ids: [demoIds(s).gazipur], fuel_types: [] },
    }),
  },
  {
    id: 'delay',
    step: 6,
    label: 'Shipment delay Gazipur +8 ticks · 64 ticks',
    hint: 'Next Gazipur arrival shows DELAYED.',
    kind: 'event',
    build: (s) => ({
      type: 'shipment_delay',
      duration_ticks: 64,
      parameters: { delay_ticks: 8, depot_ids: [demoIds(s).gazipur], fuel_types: [] },
    }),
  },
  {
    id: 'unavailable',
    step: 7,
    label: 'Unavailable 30 s',
    hint: 'Degraded banner; last good state stays on screen.',
    kind: 'fault',
    build: () => ({ type: 'unavailable', duration_seconds: 30, parameters: {} }),
  },
  {
    id: 'stale',
    step: 8,
    label: 'Stale data 60 s',
    hint: 'Stale banner; auto submissions pause.',
    kind: 'fault',
    build: () => ({ type: 'stale_data', duration_seconds: 60, parameters: {} }),
  },
  {
    id: 'stream',
    step: 8,
    label: 'Stream disconnect 60 s',
    hint: 'SSE shows disconnected; polling keeps data fresh.',
    kind: 'fault',
    build: () => ({ type: 'stream_disconnect', duration_seconds: 60, parameters: {} }),
  },
]
