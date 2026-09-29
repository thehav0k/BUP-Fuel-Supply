import { CloudLightning, LoaderCircle, Zap } from 'lucide-react'
import { api } from '@/api/client'
import { useStateQuery } from '@/api/queries'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PRESETS, type Preset } from '@/lib/demo'
import { cn } from '@/lib/utils'
import { DemoOutcomeNote } from './DemoOutcomeNote'
import { useDemoRunner } from './useDemoRunner'

export function Presets() {
  const { data: s } = useStateQuery()
  const { run, busy, outcome } = useDemoRunner()

  const fire = (p: Preset) =>
    p.kind === 'event'
      ? run(p.label, () => api.demo.createEvent(p.build(s)), () => `event injected${s?.tick != null ? ` at tick ${s.tick}` : ''}`)
      : run(p.label, () => api.demo.createFault(p.build()), () => 'fault injected')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Demo script presets</CardTitle>
        <CardDescription>One click per step of the demo script (PRD §8, steps 3–8). Events start at the current tick.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {PRESETS.map((p) => {
            const Icon = p.kind === 'event' ? Zap : CloudLightning
            return (
              <button
                key={p.id}
                type="button"
                disabled={!!busy}
                onClick={() => void fire(p)}
                className={cn(
                  'group flex cursor-pointer items-start gap-2.5 rounded-md border bg-card px-3 py-2 text-left transition-colors hover:border-primary/50 hover:bg-accent/50 disabled:cursor-not-allowed disabled:opacity-60',
                )}
              >
                <span className="tnum mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground">
                  {p.step}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-[13px] font-medium">
                    {busy === p.label ? (
                      <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
                    ) : (
                      <Icon className={cn('size-3.5', p.kind === 'event' ? 'text-warn-ink' : 'text-crit-ink')} aria-hidden />
                    )}
                    {p.label}
                  </span>
                  <span className="block text-[11px] text-muted-foreground">{p.hint}</span>
                </span>
              </button>
            )
          })}
        </div>
        <DemoOutcomeNote outcome={outcome} />
      </CardContent>
    </Card>
  )
}
