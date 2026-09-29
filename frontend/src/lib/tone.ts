import type { ComponentStatus, RiskLevel } from '@/api/types'

/**
 * Status tones. These colors carry fixed meaning (good / warning / critical)
 * and are never used as series identity. Every tone is shown with a text
 * label or icon too, never color alone.
 */
export type Tone = 'ok' | 'warn' | 'crit' | 'info' | 'neutral'

export const toneText: Record<Tone, string> = {
  ok: 'text-ok-ink',
  warn: 'text-warn-ink',
  crit: 'text-crit-ink',
  info: 'text-info-ink',
  neutral: 'text-muted-foreground',
}

/** Soft chip: tinted background + ink text + hairline ring. */
export const toneSoft: Record<Tone, string> = {
  ok: 'bg-ok/12 text-ok-ink ring-ok/30',
  warn: 'bg-warn/15 text-warn-ink ring-warn/40',
  crit: 'bg-crit/12 text-crit-ink ring-crit/35',
  info: 'bg-series-1/12 text-info-ink ring-series-1/30',
  neutral: 'bg-muted text-muted-foreground ring-border',
}

/** Solid fill for meters, dots and small marks. */
export const toneFill: Record<Tone, string> = {
  ok: 'bg-ok',
  warn: 'bg-warn',
  crit: 'bg-crit',
  info: 'bg-series-1',
  neutral: 'bg-muted-foreground/50',
}

/** Same, as CSS color values for SVG / Recharts. */
export const toneColor: Record<Tone, string> = {
  ok: 'var(--ok)',
  warn: 'var(--warn)',
  crit: 'var(--crit)',
  info: 'var(--series-1)',
  neutral: 'var(--series-muted)',
}

export function riskTone(level: RiskLevel | null | undefined): Tone {
  if (level === 'high') return 'crit'
  if (level === 'medium') return 'warn'
  if (level === 'low') return 'ok'
  return 'neutral'
}

const RISK_ORDER: Record<RiskLevel, number> = { low: 0, medium: 1, high: 2 }

export function worstRisk(levels: RiskLevel[]): RiskLevel | null {
  if (!levels.length) return null
  return levels.reduce((a, b) => (RISK_ORDER[b] > RISK_ORDER[a] ? b : a))
}

export function componentTone(status: ComponentStatus | string | null | undefined): Tone {
  if (status === 'up' || status === 'ok') return 'ok'
  if (status === 'degraded') return 'warn'
  if (status === 'down') return 'crit'
  return 'neutral'
}

export function serviceLevelTone(sl: number | null | undefined): Tone {
  if (sl === null || sl === undefined) return 'neutral'
  if (sl >= 0.98) return 'ok'
  if (sl >= 0.9) return 'warn'
  return 'crit'
}

export function allocationTone(status: string | null | undefined): Tone {
  switch (status) {
    case 'ARRIVED':
      return 'ok'
    case 'IN_TRANSIT':
    case 'PENDING':
      return 'info'
    case 'FAILED':
      return 'crit'
    default:
      return 'neutral'
  }
}

export function recStatusTone(status: string): Tone {
  switch (status) {
    case 'OPEN':
    case 'SUBMITTING':
      return 'info'
    case 'SUBMITTED':
      return 'ok'
    case 'FAILED':
      return 'crit'
    case 'EXPIRED':
    case 'SUPERSEDED':
      return 'warn'
    default:
      return 'neutral'
  }
}

export function decisionTone(action: string): Tone {
  switch (action) {
    case 'approved':
    case 'auto':
      return 'ok'
    case 'failed':
      return 'crit'
    case 'rejected':
    case 'cancelled':
      return 'warn'
    default:
      return 'neutral'
  }
}
