import { Eraser, LoaderCircle, Send } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api } from '@/api/client'
import type { FaultType } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input, Label, Select } from '@/components/ui/input'
import { FAULT_TYPES } from '@/lib/demo'
import { DemoOutcomeNote } from './DemoOutcomeNote'
import { useDemoRunner } from './useDemoRunner'

export function FaultForm() {
  const { run, busy, outcome } = useDemoRunner()
  const [type, setType] = useState<FaultType>('unavailable')
  const [duration, setDuration] = useState('30')
  const [param, setParam] = useState<Record<'delay_ms' | 'rate', string>>({ delay_ms: '500', rate: '0.25' })
  const [formError, setFormError] = useState<string | null>(null)
  const def = FAULT_TYPES.find((f) => f.type === type) ?? FAULT_TYPES[0]

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)
    const dur = Number(duration)
    if (!Number.isFinite(dur) || dur <= 0 || dur > 3600) return setFormError('Duration must be between 0 and 3600 seconds.')
    const parameters: Record<string, unknown> = {}
    if (def.param) {
      const v = Number(param[def.param.key])
      if (!Number.isFinite(v) || v < def.param.min || v > def.param.max) {
        return setFormError(`${def.param.label} must be between ${def.param.min} and ${def.param.max}.`)
      }
      parameters[def.param.key] = v
    }
    void run(
      `Inject ${def.label.toLowerCase()} fault`,
      () => api.demo.createFault({ type, duration_seconds: dur, parameters }),
      () => `active for ${dur} s`,
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inject fault</CardTitle>
        <CardDescription>{def.effect} Faults hit the simulator's /v1/* API and expire on their own.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="ft-type">Type</Label>
              <Select id="ft-type" value={type} onChange={(e) => setType(e.target.value as FaultType)}>
                {FAULT_TYPES.map((f) => (
                  <option key={f.type} value={f.type}>
                    {f.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="ft-dur">Duration (seconds)</Label>
              <Input id="ft-dur" type="number" min={1} max={3600} step={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
            </div>
            {def.param ? (
              <div className="flex flex-col gap-1">
                <Label htmlFor="ft-param">{def.param.label}</Label>
                <Input
                  id="ft-param"
                  type="number"
                  min={def.param.min}
                  max={def.param.max}
                  step={def.param.step}
                  value={param[def.param.key]}
                  onChange={(e) => setParam((p) => ({ ...p, [def.param!.key]: e.target.value }))}
                />
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" variant="destructive" disabled={!!busy}>
              {busy && busy.startsWith('Inject') ? <LoaderCircle className="animate-spin" /> : <Send />}
              Inject fault
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!!busy}
              onClick={() => void run('Clear faults', api.demo.clearFaults, () => 'all faults cleared')}
            >
              {busy === 'Clear faults' ? <LoaderCircle className="animate-spin" /> : <Eraser />}
              Clear all faults
            </Button>
            {formError ? <span className="text-xs text-crit-ink">{formError}</span> : null}
          </div>
          <DemoOutcomeNote outcome={outcome} />
        </form>
      </CardContent>
    </Card>
  )
}
