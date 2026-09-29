/**
 * Backend API types. Copied from docs/api-contract.md (the source of truth).
 * Keep this file in sync with the contract; only the small "request body" and
 * "unknown shape" helpers at the bottom are frontend additions.
 */

export type Fuel = 'DIESEL' | 'PETROL' | 'OCTANE'
export type Mode = 'manual' | 'auto' | 'hybrid' // hybrid = auto-submit low-risk/high-confidence only (PRD 9.2)
export type RiskLevel = 'low' | 'medium' | 'high' // risk >= 0.7 high, >= 0.4 medium
export type ComponentStatus = 'up' | 'degraded' | 'down'

// ---------------------------------------------------------------- GET /health

export interface Component {
  status: ComponentStatus
  detail: string
  last_ok_at: string | null
}

export interface Health {
  status: 'ok' | 'degraded'
  version: string
  grafana_url: string // e.g. "http://localhost:3001/d/fuel-ops"
  components: {
    simulator: Component & {
      breaker: 'closed' | 'open' | 'half_open'
      consecutive_failures: number
      stale: boolean
      sim_health: 'ok' | 'down'
    }
    database: Component & { pending_writes: number }
    prediction: Component & { fallback: boolean; last_latency_ms: number | null }
    sse: Component & { connected: boolean; reconnects: number; last_event_at: string | null }
    engine: Component & {
      mode: Mode
      last_cycle_tick: number | null
      last_cycle_at: string | null
      last_cycle_ms: number | null
      paused_reason: string | null
    }
  }
}

// ---------------------------------------------------------------- GET /api/state

export interface SimMetrics {
  service_level: number
  served_demand_liters: number
  unmet_demand_liters: number
  allocation_liters: number
  allocation_failures: number
}

export interface FuelView {
  fuel: Fuel
  inventory: number
  capacity: number
  fill_pct: number // 0..100
  inbound_liters: number
  inbound: { allocation_id: number; quantity: number; eta_tick: number | null; status: string; route_id: string }[]
  ticks_to_stockout: number | null // null = no stockout within horizon (48 ticks)
  hours_to_stockout: number | null
  risk: number // 0..1
  risk_level: RiskLevel
  spike: boolean
  spike_reason: string | null
  forecast_next_hour: number // liters expected over the next hour
  calibration_ratio: number
  confidence: number // 0..1
  lead_time_ticks: number
}

export interface StationView {
  id: string
  name: string
  region_id: string
  status: 'OPEN' | 'OUTAGE'
  demand_profile: string
  demand_multiplier: number
  spike: boolean // any fuel flagged
  upcoming_spike: { start_tick: number; end_tick: number; multiplier: number } | null
  primary_route_id: string | null
  fuels: FuelView[] // DIESEL, PETROL, OCTANE order
}

export interface DepotFuelView {
  fuel: Fuel
  inventory: number
  capacity: number
  fill_pct: number
  next_arrival: { tick: number; quantity: number; status: 'SCHEDULED' | 'DELAYED'; in_hours: number } | null
  projected_level_end: number // inventory + arrivals within horizon (no outbound assumed)
  reserve_liters: number // held back for own at-risk stations until next arrival
}

export interface DepotView {
  id: string
  name: string
  region_id: string
  status: 'OPEN' | 'CONSTRAINED'
  dispatch_capacity_per_tick: number
  dispatch_used_this_tick: number
  fuels: DepotFuelView[]
}

export interface RouteView {
  id: string
  source_depot_id: string
  destination_station_id: string
  transit_ticks: number
  max_shipment: number
  status: 'AVAILABLE' | 'DISRUPTED'
  is_backup: boolean // cross-region route
  scheduled_disruption: { start_tick: number; end_tick: number } | null
}

export interface Alert {
  id: string // stable, e.g. "no_route:station-tongi"
  level: 'info' | 'warning' | 'critical'
  kind: 'no_route' | 'stockout' | 'outage' | 'depot_low' | 'spike' | 'stale' | 'degraded' | 'fallback'
  message: string
  station_id?: string
  depot_id?: string
  fuel?: Fuel
}

export interface State {
  tick: number | null
  sim_time: string | null
  sim_status: 'RUNNING' | 'PAUSED' | null
  tick_minutes: number // default 15
  ticks_per_hour: number // 60 / tick_minutes
  fetched_at: string | null // wall time of last successful full sync
  data_age_s: number | null // now - fetched_at
  stale: boolean // X-Simulator-Stale seen on the last sync
  degraded: boolean // last sync failed or breaker open; data is the last good state
  degraded_reason: string | null
  fallback: boolean // prediction service down; forecasts are uncalibrated baseline
  mode: Mode
  metrics: SimMetrics | null
  stations: StationView[] // always 4 once synced, sorted mirpur, tongi, karnaphuli, coxsbazar
  depots: DepotView[]
  routes: RouteView[]
  alerts: Alert[]
  counts: { open_recommendations: number; pending_allocations: number; in_transit_allocations: number }
}

// ---------------------------------------------------------------- GET /api/forecast

export interface ForecastHistoryPoint {
  tick: number
  sim_time: string
  actual: number
  forecast: number | null
  unmet: number
}

export interface ForecastFuturePoint {
  tick: number
  sim_time: string
  forecast: number
  projected_level: number
}

export interface ForecastFuel {
  fuel: Fuel
  capacity: number
  calibration_ratio: number
  confidence: number
  history: ForecastHistoryPoint[] // last <= 96 ticks
  future: ForecastFuturePoint[] // next 48 ticks
}

export interface Forecast {
  station_id: string
  tick: number | null
  tick_minutes: number
  fallback: boolean
  fuels: ForecastFuel[]
}

// ---------------------------------------------------------------- Recommendations

export type RecStatus = 'OPEN' | 'SUBMITTING' | 'SUBMITTED' | 'REJECTED' | 'EXPIRED' | 'FAILED' | 'SUPERSEDED'

export interface Recommendation {
  id: string // "rec-<n>"
  created_tick: number
  created_at: string
  expires_tick: number
  status: RecStatus
  station_id: string
  station_name: string
  fuel: Fuel
  quantity: number
  route_id: string
  depot_id: string
  depot_name: string
  transit_ticks: number
  uses_backup_route: boolean
  reason: string // human text built from the numbers
  reason_source: 'template' | 'llm'
  risk_before: number
  risk_after: number
  risk_level_before: RiskLevel
  risk_level_after: RiskLevel
  ticks_to_stockout_before: number | null
  ticks_to_stockout_after: number | null
  confidence: number
  fallback: boolean
  caps: string[] // what limited the quantity, e.g. "route max 7,000 L"
  alternative: {
    kind: 'backup_route' | 'smaller_quantity'
    route_id: string
    depot_id: string
    quantity: number
    description: string
  } | null
  what_if: { tick: number; without: number; with: number }[] // projected station level, next 24 ticks
  auto_eligible: boolean // would hybrid mode auto-submit it
  idempotency_key: string
  allocation_id: number | null
  allocation_status: string | null
  failure_code: string | null
  failure_message: string | null
}

export interface RecommendationList {
  mode: Mode
  tick: number | null
  items: Recommendation[]
}

export interface ApiErrorBody {
  code: string
  message: string
}

export interface RecommendationActionResult {
  ok: boolean
  recommendation: Recommendation
  error: ApiErrorBody | null
}

// ---------------------------------------------------------------- Allocations

export type AllocationStatus = 'PENDING' | 'IN_TRANSIT' | 'ARRIVED' | 'FAILED' | 'CANCELLED'

export interface Allocation {
  id: number
  idempotency_key: string
  source_depot_id: string
  destination_station_id: string
  route_id: string
  fuel_type: Fuel
  quantity: number
  created_tick: number
  departure_tick: number | null
  expected_arrival_tick: number | null
  actual_arrival_tick: number | null
  status: AllocationStatus
  failure_reason: string | null
  recommendation_id: string | null
}

export interface AllocationList {
  items: Allocation[]
}

export interface CancelAllocationResult {
  ok: boolean
  allocation: Allocation | null
  error: ApiErrorBody | null
}

// ---------------------------------------------------------------- Decisions

export interface Decision {
  id: number
  recommendation_id: string
  action: 'approved' | 'rejected' | 'auto' | 'expired' | 'failed' | 'superseded' | 'cancelled'
  actor: 'operator' | 'auto' | 'system'
  tick: number | null
  created_at: string
  station_id: string
  fuel: Fuel
  quantity: number
  route_id: string
  allocation_id: number | null
  allocation_status: string | null // live, updated by the sync loop
  failure_code: string | null
  failure_reason: string | null
  note: string | null
}

export interface DecisionList {
  items: Decision[]
}

// ---------------------------------------------------------------- Events

export interface SimEvent {
  id: number
  type: string
  start_tick: number
  end_tick: number
  status: 'SCHEDULED' | 'ACTIVE' | 'RESOLVED'
  parameters: Record<string, unknown>
  description: string
}

export interface EventList {
  tick: number | null
  items: SimEvent[]
}

// ---------------------------------------------------------------- Settings

export interface Settings {
  mode: Mode
  hybrid_min_confidence: number
  hybrid_max_risk: number
}

// ---------------------------------------------------------------- Demo control (frontend helpers)

export type EventType =
  | 'demand_spike'
  | 'route_disruption'
  | 'station_outage'
  | 'depot_constraint'
  | 'shipment_delay'
  | 'supply_shortfall'

export type FaultType = 'latency' | 'unavailable' | 'error_rate' | 'stale_data' | 'stream_disconnect'

export interface CreateEventBody {
  type: EventType
  start_tick?: number
  duration_ticks: number
  parameters: Record<string, unknown>
}

export interface CreateFaultBody {
  type: FaultType
  duration_seconds: number
  parameters: Record<string, unknown>
}

export interface StepResult {
  tick: number
  sim_time: string
}

/**
 * The contract does not pin the shape of GET /api/demo/faults (it proxies the
 * simulator's /admin/faults, "last 50"). We accept either a bare array or an
 * object wrapping one, and read fields defensively.
 */
export type FaultRecord = Record<string, unknown>
export type FaultListResponse = FaultRecord[] | { items?: FaultRecord[]; faults?: FaultRecord[] }
