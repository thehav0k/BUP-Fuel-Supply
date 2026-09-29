import { ResultNote } from '@/components/ErrorNote'
import type { DemoOutcome } from './useDemoRunner'

export function DemoOutcomeNote({ outcome }: { outcome: DemoOutcome | null }) {
  if (!outcome) return null
  return (
    <ResultNote ok={outcome.ok} code={outcome.code}>
      <span className="font-medium">{outcome.label}:</span> {outcome.message}
    </ResultNote>
  )
}
