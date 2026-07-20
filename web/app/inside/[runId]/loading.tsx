// The inside view of a single run sits on the studio ground now (the
// /analytics shell — rail, white cards); the loader follows the destination.
import FilmoLoader, { GROUND_STUDIO } from '../../components/FilmoLoader'

export default function InsideRunLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
