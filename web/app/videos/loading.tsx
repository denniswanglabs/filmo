// /videos moved off the blue landing chrome and onto `LibraryShell`, whose
// `.lib-root` is the studio ground — the same daylight the rail that leads here
// already wore. The loader follows the destination, not the old surface.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function VideosLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
