const intFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const oneDp = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })

export function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  return intFmt.format(Math.round(n))
}

/** 5000 -> "5,000 L" */
export function fmtLiters(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  return `${intFmt.format(Math.round(n))} L`
}

/** 45200 -> "45.2k L" (for tight spaces like axis ticks and meters) */
export function fmtLitersCompact(n: number | null | undefined, unit = true): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  const abs = Math.abs(n)
  const s = abs >= 1_000_000 ? `${oneDp.format(n / 1_000_000)}M` : abs >= 1000 ? `${oneDp.format(n / 1000)}k` : intFmt.format(n)
  return unit ? `${s} L` : s
}

/** Fraction 0..1 -> "87%" (digits configurable) */
export function fmtPct(fraction: number | null | undefined, digits = 0): string {
  if (fraction === null || fraction === undefined || !Number.isFinite(fraction)) return '—'
  return `${(fraction * 100).toFixed(digits)}%`
}

/** Already 0..100 -> "62%" */
export function fmtPct100(pct: number | null | undefined, digits = 0): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return '—'
  return `${pct.toFixed(digits)}%`
}

export function fmtMultiplier(m: number): string {
  return `×${parseFloat(m.toFixed(2))}`
}

/** Hours to a short label. null => beyond the forecast horizon. */
export function fmtHours(hours: number | null | undefined, horizonHours = 12): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return `> ${oneDp.format(horizonHours)}h`
  if (hours <= 0) return 'now'
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`
  return `${oneDp.format(hours)}h`
}

export function ticksToHours(ticks: number | null | undefined, ticksPerHour: number): number | null {
  if (ticks === null || ticks === undefined || !Number.isFinite(ticks) || ticksPerHour <= 0) return null
  return ticks / ticksPerHour
}

/** Duration of N ticks as wall-sim time: 2 ticks @15min -> "30 min", 10 -> "2h 30m" */
export function fmtTickSpan(ticks: number, tickMinutes: number): string {
  const mins = Math.round(ticks * tickMinutes)
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m ? `${h}h ${m}m` : `${h}h`
}

function pad2(n: number) {
  return String(n).padStart(2, '0')
}

/** "Day 1 · 03:15". Day = floor(tick / (ticks_per_hour * 24)) + 1. */
export function fmtSimClock(
  tick: number | null,
  simTime: string | null,
  ticksPerHour: number,
  tickMinutes: number,
): string {
  if (tick === null) return '—'
  const tpd = Math.max(1, ticksPerHour * 24)
  const day = Math.floor(tick / tpd) + 1
  let hhmm: string
  const m = simTime?.match(/T(\d{2}):(\d{2})/)
  if (m) {
    hhmm = `${m[1]}:${m[2]}`
  } else {
    const minsIntoDay = Math.round((tick % tpd) * tickMinutes)
    hhmm = `${pad2(Math.floor(minsIntoDay / 60) % 24)}:${pad2(minsIntoDay % 60)}`
  }
  return `Day ${day} · ${hhmm}`
}

/** Seconds -> "just now" / "12s ago" / "3m ago" / "2h ago" */
export function fmtAgo(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, seconds)
  if (s < 2) return 'just now'
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`
  return `${Math.floor(s / 86400)}d ago`
}

/** Seconds -> "4s" / "2m 5s" (no "ago") */
export function fmtSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export function secondsSince(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return null
  return (now - t) / 1000
}

export function fmtRelative(iso: string | null | undefined, now: number): string {
  return fmtAgo(secondsSince(iso, now))
}

/** ISO wall time -> local "14:03:21" (or with date when not today) */
export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString([], { hour12: false })
}

/** "route_disruption" -> "Route disruption", "IN_TRANSIT" -> "In transit" */
export function humanize(s: string | null | undefined): string {
  if (!s) return ''
  const t = s.replace(/[_-]+/g, ' ').trim().toLowerCase()
  return t.charAt(0).toUpperCase() + t.slice(1)
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—'
  return ms < 10 ? `${ms.toFixed(1)} ms` : `${Math.round(ms)} ms`
}
