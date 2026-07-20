// The run route's boot screen — the gap between "clicked a film" and "the
// workspace is on screen" is a Filmo screen rather than a white flash or,
// worse, a workspace full of invented progress.
//
// The screen itself now lives in `app/components/FilmoLoader.tsx`; this file
// was where it was first built, and it moved out the moment a second route
// needed it. Its defaults ARE this screen — the studio ground, the full
// viewport, the 50px mark — so `<FilmoLoader />` renders exactly what was
// approved here. Both of the deviations this file used to document are now
// properties of the shared component and are explained there: it is a flow
// block rather than `position:fixed` (the route template's transform would
// hijack fixed positioning), and it has no fade-out class because React
// unmounts the boundary when the segment is ready.
import FilmoLoader from '../../components/FilmoLoader'

export default function RunLoading() {
  return <FilmoLoader />
}
