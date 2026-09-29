import { ChevronsRight, LoaderCircle, Pause, Play, RotateCcw, StepForward } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import { useStateQuery } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { fmtSimClock } from '@/lib/format'
import { DemoOutcomeNote } from './DemoOutcomeNote'
import { useDemoRunner } from './useDemoRunner'

export function ClockControls() {
  const { data: s } = useStateQuery()
  const { run, busy, outcome } = useDemoRunner()
  const [confirmReset, setConfirmReset] = useState(false)
  const tph = s?.ticks_per_hour ?? 4
  const tm = s?.tick_minutes ?? 15
  const icon = (label: string, Icon: typeof Play) => (busy === label ? <LoaderCircle className="animate-spin" /> : <Icon />)

  const step = (count: number) =>
    run(`Step ${count}`, () => api.demo.step(count), (r) => `now at tick ${r.tick} (${fmtSimClock(r.tick, r.sim_time, tph, tm)})`)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Simulation clock</CardTitle>
          {s?.sim_status ? <Badge tone={s.sim_status === 'RUNNING' ? 'ok' : 'warn'}>{s.sim_status}</Badge> : null}
        </div>
        <CardDescription>
          Tick <span className="tnum font-medium text-foreground">{s?.tick ?? '—'}</span>
          {s ? ` · ${fmtSimClock(s.tick, s.sim_time, tph, tm)}` : ''}. Pause and step for a followable demo.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="success" disabled={!!busy} onClick={() => run('Run', api.demo.run, () => 'simulation running')}>
            {icon('Run', Play)} Run
          </Button>
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run('Pause', api.demo.pause, () => 'simulation paused')}>
            {icon('Pause', Pause)} Pause
          </Button>
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => step(1)}>
            {icon('Step 1', StepForward)} Step 1
          </Button>
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => step(10)}>
            {icon('Step 10', ChevronsRight)} Step 10
          </Button>
          {confirmReset ? (
            <span className="inline-flex items-center gap-1.5 rounded-md bg-crit/10 px-2 py-0.5 text-xs text-crit-ink ring-1 ring-crit/30 ring-inset">
              Reset the whole world?
              <Button
                size="xs"
                variant="destructive"
                disabled={!!busy}
                onClick={() => {
                  setConfirmReset(false)
                  void run('Reset', api.demo.reset, () => 'simulator reset to tick 0')
                }}
              >
                Yes, reset
              </Button>
              <Button size="xs" variant="ghost" onClick={() => setConfirmReset(false)}>
                No
              </Button>
            </span>
          ) : (
            <Button size="sm" variant="outline" className="text-crit-ink" disabled={!!busy} onClick={() => setConfirmReset(true)}>
              {icon('Reset', RotateCcw)} Reset
            </Button>
          )}
        </div>
        <DemoOutcomeNote outcome={outcome} />
      </CardContent>
    </Card>
  )
}
