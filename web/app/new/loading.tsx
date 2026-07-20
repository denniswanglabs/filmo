// /new is the composer with the studio's rail beside it, on the studio ground
// (`.nw-root`) — the same daylight /overview, /videos and /assets wear. The
// loader takes that ground too, so the hand-off is a dissolve, not a flash.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function NewFilmoLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
