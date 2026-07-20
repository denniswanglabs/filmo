// Sign-in is one small card on the studio ground (`.lgn-root`), and the page
// itself holds the same compact loader while the session resolves — so the
// route boundary and the page agree, and the wait is one continuous screen.
// Compact because the wait is short: present and deliberate, not heavy.
import FilmoLoader, { GROUND_STUDIO } from '../components/FilmoLoader'

export default function LoginLoading() {
  return <FilmoLoader ground={GROUND_STUDIO} size="compact" />
}
