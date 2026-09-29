import { useSyncExternalStore } from 'react'

export const SCREENS = ['network', 'recommendations', 'history', 'health', 'demo'] as const
export type Screen = (typeof SCREENS)[number]

export interface Route {
  screen: Screen
  /** Optional sub-path, e.g. the selected station id in #/network/station-mirpur */
  param: string | null
}

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const screen = (SCREENS as readonly string[]).includes(parts[0] ?? '') ? (parts[0] as Screen) : 'network'
  return { screen, param: parts[1] ? decodeURIComponent(parts[1]) : null }
}

function subscribe(cb: () => void) {
  window.addEventListener('hashchange', cb)
  return () => window.removeEventListener('hashchange', cb)
}

const getHash = () => window.location.hash

export function useHashRoute(): Route {
  const hash = useSyncExternalStore(subscribe, getHash, () => '')
  return parse(hash)
}

export function href(screen: Screen, param?: string | null): string {
  return `#/${screen}${param ? `/${encodeURIComponent(param)}` : ''}`
}

export function navigate(screen: Screen, param?: string | null) {
  window.location.hash = href(screen, param)
}
