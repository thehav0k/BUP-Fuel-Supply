import { Banners } from '@/components/Banners'
import { NavTabs } from '@/components/NavTabs'
import { TopBar } from '@/components/TopBar'
import { useHashRoute } from '@/lib/router'
import { DemoScreen } from '@/screens/DemoScreen'
import { HealthScreen } from '@/screens/HealthScreen'
import { HistoryScreen } from '@/screens/HistoryScreen'
import { NetworkScreen } from '@/screens/NetworkScreen'
import { RecommendationsScreen } from '@/screens/RecommendationsScreen'

export function App() {
  const route = useHashRoute()
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 border-b bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/85">
        <TopBar />
        <NavTabs current={route.screen} />
        <Banners />
      </header>
      <main className="mx-auto w-full max-w-[1800px] px-4 py-4">
        {route.screen === 'network' ? <NetworkScreen selectedStation={route.param} /> : null}
        {route.screen === 'recommendations' ? <RecommendationsScreen /> : null}
        {route.screen === 'history' ? <HistoryScreen /> : null}
        {route.screen === 'health' ? <HealthScreen /> : null}
        {route.screen === 'demo' ? <DemoScreen /> : null}
      </main>
    </div>
  )
}
