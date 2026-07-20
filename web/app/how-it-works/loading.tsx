// /how-it-works is a chapter of the landing now, on the landing's night — the
// loader follows the destination (same ground as app/loading.tsx, the route
// the reader almost always arrives from), so the hand-off is a dissolve
// rather than a white flash.
import FilmoLoader, { GROUND_NIGHT } from '../components/FilmoLoader'

export default function HowItWorksLoading() {
  return <FilmoLoader ground={GROUND_NIGHT} />
}
