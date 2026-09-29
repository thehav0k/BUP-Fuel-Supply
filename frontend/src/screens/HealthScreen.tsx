import { Brain, CloudOff, Cpu, Database, ExternalLink, Radio, Server } from 'lucide-react'
import { useHealthQuery } from '@/api/queries'
import { EmptyState } from '@/components/EmptyState'
import { ComponentCard, KV } from '@/components/health/ComponentCard'
import { ComponentStatusBadge } from '@/components/StatusBadges'
import { Card } from '@/components/ui/card'
import { LinkButton } from '@/components/ui/button'
import { useNow } from '@/lib/clock'
import { fmtAgo, fmtMs, fmtRelative, humanize } from '@/lib/format'

export function HealthScreen() {
  const { data: h, isError, error, dataUpdatedAt } = useHealthQuery()
  const now = useNow()

  if (!h) {
    return isError ? (
      <EmptyState icon={CloudOff} title="Backend unreachable">
        GET /health failed ({error instanceof Error ? error.message : 'unknown error'}). Retrying every 2 s.
      </EmptyState>
    ) : (
      <EmptyState spin title="Checking system health…" />
    )
  }

  const c = h.components
  const overall = isError ? 'down' : h.status === 'ok' ? 'up' : 'degraded'

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Overall</span>
          <ComponentStatusBadge status={overall} size="lg" />
        </div>
        <div className="text-xs text-muted-foreground">
          version <span className="font-mono text-foreground">{h.version}</span>
        </div>
        <div className="text-xs text-muted-foreground">
          checked {isError ? <span className="text-crit-ink">failing; last OK {fmtAgo((now - dataUpdatedAt) / 1000)}</span> : fmtAgo((now - dataUpdatedAt) / 1000)}
        </div>
        <LinkButton href={h.grafana_url} target="_blank" rel="noopener noreferrer" variant="outline" size="sm" className="ml-auto">
          <ExternalLink />
          Open Grafana dashboard
        </LinkButton>
      </Card>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        <ComponentCard title="Simulator" icon={Server} component={c.simulator}>
          <KV k="Circuit breaker" tone={c.simulator.breaker === 'closed' ? 'ok' : c.simulator.breaker === 'open' ? 'crit' : 'warn'}>
            {humanize(c.simulator.breaker)}
          </KV>
          <KV k="Consecutive failures" tone={c.simulator.consecutive_failures > 0 ? 'warn' : undefined}>
            {c.simulator.consecutive_failures}
          </KV>
          <KV k="Stale data" tone={c.simulator.stale ? 'warn' : undefined}>
            {c.simulator.stale ? 'yes' : 'no'}
          </KV>
          <KV k="Simulator /v1/health" tone={c.simulator.sim_health === 'ok' ? 'ok' : 'crit'}>
            {c.simulator.sim_health}
          </KV>
        </ComponentCard>

        <ComponentCard title="Database" icon={Database} component={c.database}>
          <KV k="Pending writes" tone={c.database.pending_writes > 0 ? 'warn' : undefined}>
            {c.database.pending_writes}
          </KV>
        </ComponentCard>

        <ComponentCard title="Prediction service" icon={Brain} component={c.prediction}>
          <KV k="Fallback forecast" tone={c.prediction.fallback ? 'warn' : 'ok'}>
            {c.prediction.fallback ? 'active' : 'off'}
          </KV>
          <KV k="Last latency">{fmtMs(c.prediction.last_latency_ms)}</KV>
        </ComponentCard>

        <ComponentCard title="SSE stream" icon={Radio} component={c.sse}>
          <KV k="Connected" tone={c.sse.connected ? 'ok' : 'crit'}>
            {c.sse.connected ? 'yes' : 'no (polling continues)'}
          </KV>
          <KV k="Reconnects">{c.sse.reconnects}</KV>
          <KV k="Last event">{c.sse.last_event_at ? fmtRelative(c.sse.last_event_at, now) : 'never'}</KV>
        </ComponentCard>

        <ComponentCard title="Decision engine" icon={Cpu} component={c.engine}>
          <KV k="Mode">{humanize(c.engine.mode)}</KV>
          <KV k="Last cycle tick">{c.engine.last_cycle_tick ?? '—'}</KV>
          <KV k="Last cycle">{c.engine.last_cycle_at ? fmtRelative(c.engine.last_cycle_at, now) : 'never'}</KV>
          <KV k="Cycle time">{fmtMs(c.engine.last_cycle_ms)}</KV>
          <KV k="Paused" tone={c.engine.paused_reason ? 'warn' : undefined}>
            {c.engine.paused_reason ?? 'no'}
          </KV>
        </ComponentCard>
      </div>
    </div>
  )
}
