import { useHash } from './useHash'
import { Home } from './screens/Home'
import { Materials } from './screens/Materials'

export default function App() {
  const [a, vid, screen] = useHash()
  if (a === 'v' && vid && screen === 'materials') return <Materials vid={vid} />
  return <Home />
}
