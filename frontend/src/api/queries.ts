import {
  keepPreviousData,
  QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import { api } from './client'
import type { CreateEventBody, CreateFaultBody, Mode, Settings, State } from './types'

export const POLL_MS = 2000

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: POLL_MS,
      // Keep the last good data on screen across refetches, key changes and errors.
      placeholderData: keepPreviousData,
      staleTime: 1000,
      retry: 1,
      retryDelay: 700,
      refetchOnWindowFocus: true,
    },
    mutations: { retry: 0 },
  },
})

export const qk = {
  state: ['state'] as const,
  health: ['health'] as const,
  settings: ['settings'] as const,
  forecast: (stationId: string) => ['forecast', stationId] as const,
  recommendations: (status: 'open' | 'all') => ['recommendations', status] as const,
  allocations: ['allocations'] as const,
  decisions: ['decisions'] as const,
  events: ['events'] as const,
  faults: ['demo', 'faults'] as const,
}

// ------------------------------------------------------------------ queries

export const useStateQuery = () => useQuery({ queryKey: qk.state, queryFn: ({ signal }) => api.state(signal) })

export const useHealthQuery = () => useQuery({ queryKey: qk.health, queryFn: ({ signal }) => api.health(signal) })

export const useSettingsQuery = () =>
  useQuery({ queryKey: qk.settings, queryFn: ({ signal }) => api.settings(signal), refetchInterval: 5000 })

export const useForecastQuery = (stationId: string | null) =>
  useQuery({
    queryKey: qk.forecast(stationId ?? ''),
    queryFn: ({ signal }) => api.forecast(stationId as string, signal),
    enabled: !!stationId,
    // A different station should not flash the previous station's chart.
    placeholderData: undefined,
  })

export const useRecommendationsQuery = (status: 'open' | 'all') =>
  useQuery({ queryKey: qk.recommendations(status), queryFn: ({ signal }) => api.recommendations(status, signal) })

export const useAllocationsQuery = () =>
  useQuery({ queryKey: qk.allocations, queryFn: ({ signal }) => api.allocations(50, signal) })

export const useDecisionsQuery = () =>
  useQuery({ queryKey: qk.decisions, queryFn: ({ signal }) => api.decisions(100, signal) })

export const useEventsQuery = () => useQuery({ queryKey: qk.events, queryFn: ({ signal }) => api.events(signal) })

export const useFaultsQuery = () => useQuery({ queryKey: qk.faults, queryFn: ({ signal }) => api.demo.faults(signal) })

// ------------------------------------------------------------------ mutations

function useInvalidate() {
  const qc = useQueryClient()
  return (keys: QueryKey[]) => Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })))
}

export function useSetMode() {
  const qc = useQueryClient()
  const invalidate = useInvalidate()
  return useMutation({
    mutationKey: ['set-mode'],
    mutationFn: (mode: Mode) => api.setMode(mode),
    onSuccess: (settings: Settings) => {
      qc.setQueryData(qk.settings, settings)
      qc.setQueryData<State>(qk.state, (prev) => (prev ? { ...prev, mode: settings.mode } : prev))
    },
    onSettled: () => invalidate([qk.settings, qk.state, ['recommendations'], qk.health]),
  })
}

export type RecAction = { id: string; action: 'approve' | 'reject'; note?: string }

export function useRecommendationAction() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationKey: ['rec-action'],
    mutationFn: ({ id, action, note }: RecAction) => (action === 'approve' ? api.approve(id) : api.reject(id, note)),
    onSettled: () => invalidate([['recommendations'], qk.state, qk.decisions, qk.allocations]),
  })
}

export function useCancelAllocation() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationKey: ['cancel-allocation'],
    mutationFn: (id: number) => api.cancelAllocation(id),
    onSettled: () => invalidate([qk.allocations, qk.decisions, qk.state, ['recommendations']]),
  })
}

/** Demo-control calls change the whole world, so refresh everything afterwards. */
export function useDemoMutation<TVars, TResult>(key: string, fn: (vars: TVars) => Promise<TResult>) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: ['demo', key],
    mutationFn: fn,
    onSettled: () => qc.invalidateQueries(),
  })
}

export const demoFns = {
  run: () => api.demo.run(),
  pause: () => api.demo.pause(),
  step: (count: number) => api.demo.step(count),
  reset: () => api.demo.reset(),
  createEvent: (body: CreateEventBody) => api.demo.createEvent(body),
  createFault: (body: CreateFaultBody) => api.demo.createFault(body),
  clearFaults: () => api.demo.clearFaults(),
}
