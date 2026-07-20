// The editor's own canvas is white (`.ws-editor-root { --bg:#FFFFFF }`), and so
// is the chrome around its not-ready states — so the loader is white here, not
// the studio ground the run route itself uses.
import FilmoLoader, { GROUND_LIGHT } from '../../../components/FilmoLoader'

export default function EditRunLoading() {
  return <FilmoLoader ground={GROUND_LIGHT} />
}
