// `/` is the landing, and the landing is a screening room — PloyLanding pins
// the body to night for exactly as long as it is mounted. The loader matches
// that ground rather than the app's white, so arriving at the front door is a
// dissolve instead of a white flash.
//
// This is also the fallback boundary for any future route that ships without
// its own loading.tsx. Every route that exists today has one, so if this
// screen ever appears somewhere dark-grounded and unexpected, the fix is to
// give that route its own — not to neutralise this ground.
import FilmoLoader, { GROUND_NIGHT } from './components/FilmoLoader'

export default function RootLoading() {
  return <FilmoLoader ground={GROUND_NIGHT} />
}
