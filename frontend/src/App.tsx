import { useHash } from './useHash'
import { Home } from './screens/Home'
import { Materials } from './screens/Materials'
import { CourseMap } from './screens/CourseMap'
import { Assessments } from './screens/Assessments'

export default function App() {
  const [a, vid, screen] = useHash()
  if (a === 'v' && vid && screen === 'materials') return <Materials vid={vid} />
  if (a === 'v' && vid && screen === 'map') return <CourseMap vid={vid} />
  if (a === 'v' && vid && screen === 'assessments') return <Assessments vid={vid} />
  return <Home />
}
