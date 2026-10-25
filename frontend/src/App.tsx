import { useHash } from './useHash'
import { Home } from './screens/Home'
import { Materials } from './screens/Materials'
import { CourseMap } from './screens/CourseMap'
import { Assessments } from './screens/Assessments'
import { Review } from './screens/Review'
import { Summary } from './screens/Summary'
import { Method } from './screens/Method'

export default function App() {
  const [a, vid, screen, qid] = useHash()
  if (a === 'v' && vid && screen === 'materials') return <Materials vid={vid} />
  if (a === 'v' && vid && screen === 'map') return <CourseMap vid={vid} />
  if (a === 'v' && vid && screen === 'assessments') return <Assessments vid={vid} />
  if (a === 'v' && vid && screen === 'review') return <Review vid={vid} qid={qid} />
  if (a === 'v' && vid && screen === 'summary') return <Summary vid={vid} />
  if (a === 'v' && vid && screen === 'method') return <Method vid={vid} />
  return <Home />
}
