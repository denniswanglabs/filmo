// /assets renders inside `LibraryShell`, whose `.lib-root` is the studio ground
// — so is its sibling /videos, and so is the rail that leads to both.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function AssetsLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} />
}
