// Analytics moved off the white TopBar chrome and onto the Overview's shell —
// studio ground, white cards, the rail. The loader follows the destination.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function AnalyticsLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
