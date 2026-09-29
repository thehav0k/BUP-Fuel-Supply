import { Bot, Hand, Scale } from 'lucide-react'
import { errorInfo } from '@/api/client'
import { useSetMode, useStateQuery } from '@/api/queries'
import type { Mode } from '@/api/types'
import { Segmented, type SegmentOption } from '@/components/ui/segmented'
import { MODE_INFO } from '@/lib/modes'
import { cn } from '@/lib/utils'

const OPTIONS: SegmentOption<Mode>[] = [
  { value: 'manual', label: <><Hand className="size-3.5" aria-hidden />Manual</>, title: MODE_INFO.manual.blurb },
  { value: 'auto', label: <><Bot className="size-3.5" aria-hidden />Auto</>, title: MODE_INFO.auto.blurb },
  { value: 'hybrid', label: <><Scale className="size-3.5" aria-hidden />Hybrid</>, title: MODE_INFO.hybrid.blurb },
]

/** manual / auto / hybrid segmented control, backed by PUT /api/settings. */
export function ModeToggle({ size = 'default', className }: { size?: 'sm' | 'default'; className?: string }) {
  const { data } = useStateQuery()
  const setMode = useSetMode()
  const shown = setMode.isPending ? setMode.variables : data?.mode
  return (
    <div className={cn('flex flex-col items-end gap-0.5', className)}>
      <Segmented<Mode>
        ariaLabel="Decision mode"
        value={shown}
        options={OPTIONS}
        size={size}
        disabled={!data || setMode.isPending}
        onChange={(m) => setMode.mutate(m)}
      />
      {setMode.isError ? (
        <span className="text-[11px] text-crit-ink" role="alert">
          Mode change failed: {errorInfo(setMode.error).code}
        </span>
      ) : null}
    </div>
  )
}
