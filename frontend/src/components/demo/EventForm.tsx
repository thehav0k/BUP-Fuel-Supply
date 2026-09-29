import { LoaderCircle, Send } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api } from '@/api/client'
import { useStateQuery } from '@/api/queries'
import type { CreateEventBody, EventType } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChipSelect } from '@/components/ui/chip-select'
import { Input, Label, Select } from '@/components/ui/input'
import { EVENT_TYPES, LIST_LABEL, type ListParam, type NumParam } from '@/lib/demo'
import { FUELS, useWorld } from '@/lib/world'
import { DemoOutcomeNote } from './DemoOutcomeNote'
import { useDemoRunner } from './useDemoRunner'

type Lists = Record<ListParam, string[]>
const EMPTY_LISTS: Lists = { region_ids: [], station_ids: [], route_ids: [], depot_ids: [], fuel_types: [] }

export function EventForm() {
  const { data: s } = useStateQuery()
  const world = useWorld()
  const { run, busy, outcome } = useDemoRunner()

  const [type, setType] = useState<EventType>('demand_spike')
  const [startTick, setStartTick] = useState('')
  const [duration, setDuration] = useState('32')
  const [nums, setNums] = useState<Record<NumParam, string>>({ multiplier: '1.5', delay_ticks: '2', factor: '0.5' })
  const [lists, setLists] = useState<Lists>(EMPTY_LISTS)
  const [formError, setFormError] = useState<string | null>(null)

  const def = EVENT_TYPES.find((e) => e.type === type) ?? EVENT_TYPES[0]

  const options: Record<ListParam, { value: string; label: string }[]> = {
    region_ids: world.regionIds.map((id) => ({ value: id, label: world.regionName(id) })),
    station_ids: world.stationIds.map((id) => ({ value: id, label: world.stationName(id) })),
    route_ids: (s?.routes ?? []).map((r) => ({ value: r.id, label: `${world.routeLabel(r.id)}${r.is_backup ? ' (backup)' : ''}` })),
    depot_ids: world.depotIds.map((id) => ({ value: id, label: world.depotName(id) })),
    fuel_types: FUELS.map((f) => ({ value: f, label: f })),
  }

  const onTypeChange = (t: EventType) => {
    setType(t)
    const d = EVENT_TYPES.find((e) => e.type === t)
    if (d) setDuration(String(d.defaultDuration))
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)
    const dur = Number(duration)
    if (!Number.isInteger(dur) || dur <= 0) return setFormError('Duration must be a whole number of ticks > 0.')
    let start: number | undefined
    if (startTick.trim() !== '') {
      start = Number(startTick)
      if (!Number.isInteger(start) || start < 0) return setFormError('Start tick must be a whole number ≥ 0.')
    }
    const parameters: Record<string, unknown> = {}
    for (const n of def.nums) {
      const v = Number(nums[n.key])
      if (!Number.isFinite(v) || v < n.min || (n.max !== undefined && v > n.max) || (n.integer && !Number.isInteger(v))) {
        return setFormError(`${n.label} must be ${n.integer ? 'a whole number ' : ''}between ${n.min} and ${n.max ?? '∞'}.`)
      }
      parameters[n.key] = v
    }
    for (const l of def.lists) parameters[l] = lists[l]
    const body: CreateEventBody = { type, duration_ticks: dur, parameters, ...(start !== undefined ? { start_tick: start } : {}) }
    void run(
      `Inject ${def.label.toLowerCase()}`,
      () => api.demo.createEvent(body),
      () => `scheduled from tick ${start ?? s?.tick ?? 'now'} for ${dur} ticks`,
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Inject event</CardTitle>
        <CardDescription>{def.effect} Empty selections mean “all”.</CardDescription>
      </CardHeader>
      <CardContent>
        <form className="flex flex-col gap-3" onSubmit={submit}>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="ev-type">Type</Label>
              <Select id="ev-type" value={type} onChange={(e) => onTypeChange(e.target.value as EventType)}>
                {EVENT_TYPES.map((t) => (
                  <option key={t.type} value={t.type}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="ev-start">Start tick</Label>
              <Input
                id="ev-start"
                inputMode="numeric"
                placeholder={s?.tick != null ? `now (${s.tick})` : 'now'}
                value={startTick}
                onChange={(e) => setStartTick(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="ev-dur">Duration (ticks)</Label>
              <Input id="ev-dur" type="number" min={1} step={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
            </div>
            {def.nums.map((n) => (
              <div key={n.key} className="flex flex-col gap-1">
                <Label htmlFor={`ev-${n.key}`}>{n.label}</Label>
                <Input
                  id={`ev-${n.key}`}
                  type="number"
                  min={n.min}
                  max={n.max}
                  step={n.step}
                  value={nums[n.key]}
                  onChange={(e) => setNums((p) => ({ ...p, [n.key]: e.target.value }))}
                />
              </div>
            ))}
          </div>

          {def.lists.map((l) => (
            <div key={l} className="flex flex-col gap-1">
              <Label>
                {LIST_LABEL[l]} <span className="font-normal">({lists[l].length ? `${lists[l].length} selected` : 'all'})</span>
              </Label>
              <ChipSelect
                ariaLabel={LIST_LABEL[l]}
                options={options[l]}
                value={lists[l]}
                onChange={(next) => setLists((p) => ({ ...p, [l]: next }))}
              />
            </div>
          ))}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="sm" disabled={!!busy}>
              {busy ? <LoaderCircle className="animate-spin" /> : <Send />}
              Inject event
            </Button>
            {formError ? <span className="text-xs text-crit-ink">{formError}</span> : null}
          </div>
          <DemoOutcomeNote outcome={outcome} />
        </form>
      </CardContent>
    </Card>
  )
}
