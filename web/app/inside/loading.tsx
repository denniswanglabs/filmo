// Developer mode moved off the white TopBar chrome and onto the /analytics
// shell — studio ground, white card, the rail. The loader follows the
// destination.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function InsideLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
