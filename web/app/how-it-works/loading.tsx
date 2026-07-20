// A static explainer: the server component itself renders instantly, but its
// sections are animated client components, so a client-side navigation here
// still has chunks to fetch. Compact for the same reason as /login — the wait
// is short and the loader should look deliberate rather than heavy.
import FilmoLoader, { GROUND_LIGHT } from '../components/FilmoLoader'

export default function HowItWorksLoading() {
  return <FilmoLoader ground={GROUND_LIGHT} size="compact" />
}
