import { useState } from 'react'
import { errorInfo } from '@/api/client'
import { useDemoAction } from '@/api/queries'

export interface DemoOutcome {
  ok: boolean
  label: string
  code: string | null
  message: string
}

/** Runs a demo-control call, remembers its outcome for inline display, and refreshes all queries. */
export function useDemoRunner() {
  const m = useDemoAction()
  const [outcome, setOutcome] = useState<DemoOutcome | null>(null)
  const run = <T,>(label: string, fn: () => Promise<T>, describe?: (res: T) => string) => {
    setOutcome(null)
    return m
      .mutateAsync({ label, fn })
      .then((res) => setOutcome({ ok: true, label, code: null, message: describe ? describe(res as T) : 'done' }))
      .catch((err: unknown) => setOutcome({ ok: false, label, ...errorInfo(err) }))
  }
  return { run, busy: m.isPending ? (m.variables?.label ?? null) : null, outcome }
}
