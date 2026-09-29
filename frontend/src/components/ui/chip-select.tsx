import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Multi-select as toggle chips. Good for small, known id sets. */
export function ChipSelect({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: string; label: string }[]
  value: string[]
  onChange: (next: string[]) => void
  ariaLabel: string
}) {
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  return (
    <div role="group" aria-label={ariaLabel} className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o.value)
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => toggle(o.value)}
            title={o.value}
            className={cn(
              'inline-flex cursor-pointer items-center gap-1 rounded-full px-2.5 py-0.5 text-xs ring-1 ring-inset transition-colors',
              on ? 'bg-primary/12 font-medium text-info-ink ring-primary/50' : 'text-muted-foreground ring-border hover:bg-accent',
            )}
          >
            {on ? <Check className="size-3" aria-hidden /> : null}
            {o.label}
          </button>
        )
      })}
      {options.length === 0 ? <span className="text-xs text-muted-foreground">none known yet</span> : null}
    </div>
  )
}
