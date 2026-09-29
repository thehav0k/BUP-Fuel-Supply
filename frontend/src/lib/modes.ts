import type { Mode } from '@/api/types'

export const MODE_INFO: Record<Mode, { label: string; blurb: string }> = {
  manual: { label: 'Manual', blurb: 'Every recommendation waits for an operator to approve or reject it.' },
  auto: {
    label: 'Auto',
    blurb: 'The engine submits every recommendation itself (paused while data is stale or the simulator breaker is open).',
  },
  hybrid: {
    label: 'Hybrid',
    blurb: 'Low-risk, high-confidence recommendations are auto-submitted; high-risk or fallback ones wait for a human.',
  },
}

export const MODES: Mode[] = ['manual', 'auto', 'hybrid']
