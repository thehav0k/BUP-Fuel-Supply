import { ActiveFaults } from '@/components/demo/ActiveFaults'
import { ClockControls } from '@/components/demo/ClockControls'
import { EventForm } from '@/components/demo/EventForm'
import { FaultForm } from '@/components/demo/FaultForm'
import { Presets } from '@/components/demo/Presets'

export function DemoScreen() {
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="flex flex-col gap-4">
        <ClockControls />
        <Presets />
      </div>
      <div className="flex flex-col gap-4">
        <EventForm />
        <FaultForm />
        <ActiveFaults />
      </div>
    </div>
  )
}
