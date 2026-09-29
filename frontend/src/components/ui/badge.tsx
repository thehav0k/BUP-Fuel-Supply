import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { toneSoft, type Tone } from '@/lib/tone'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center gap-1 whitespace-nowrap rounded-md font-medium ring-1 ring-inset [&_svg]:size-3 [&_svg]:shrink-0',
  {
    variants: {
      size: {
        default: 'px-1.5 py-0.5 text-xs',
        sm: 'px-1 py-px text-[10px] uppercase tracking-wide',
        lg: 'px-2 py-1 text-sm',
      },
    },
    defaultVariants: { size: 'default' },
  },
)

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  tone?: Tone
}

export function Badge({ className, tone = 'neutral', size, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ size }), toneSoft[tone], className)} {...props} />
}
