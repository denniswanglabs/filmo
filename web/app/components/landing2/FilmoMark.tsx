// ── FILMO'S OWN MARK ────────────────────────────────────────────────────────
// The canonical blob path, byte-identical to the one `Wordmark` ships in
// `app/components/Brand.tsx` (and to the studio chrome's copy in
// runs/[id]/Workspace.tsx). It lives here as a bare path rather than as a call
// to `Wordmark` because this landing needs sizes Wordmark does not offer — a
// 39px mark beside 28.5px type in the nav, 50px in the boot screen, 38px for
// the mark that wanders the browsing frame — and because the browsing mark is
// drawn in the landing's lighter accent (#4B8DF8), not the product blue.
//
// What it must NEVER become is a CSS impression of the logo. The rule this
// component exists to enforce: an approximation drifts the moment the real mark
// changes, and nobody notices for weeks. A copied path can be wrong exactly
// once, visibly, and a diff finds it.
const BLOB =
  'M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z'

export default function FilmoMark({
  className,
  fill = '#3B82F6',
}: {
  className?: string
  fill?: string
}) {
  return (
    <svg viewBox="14 13 56 56" aria-hidden="true" className={className}>
      <path fillRule="evenodd" fill={fill} d={BLOB} />
    </svg>
  )
}
