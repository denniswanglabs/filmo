// The signed-in home sits on the studio's daylight (`.ov-root`), so its loader
// does too — the hand-off is a dissolve, not a flash.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function OverviewLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
