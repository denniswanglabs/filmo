'use client'
// ═══════════════════════ /videos — THE FILMO LIBRARY ═════════════════════════
//
// Every filmo this account has started, newest first.
//
// ── WHAT CHANGED, AND WHAT DELIBERATELY DID NOT (2026-07-19) ────────────────
// Like /assets, this page wore the old blue landing chrome — FloatingNav,
// SiteFooter, LandingBackdrop — while the rail that leads here had already
// moved to the studio ground. The rail lists Filmos and Assets one line apart,
// so one rebuilt sibling and one un-rebuilt sibling is a difference the reader
// meets in a single click. Both now render inside the same LibraryShell, which
// is what makes "they match" a fact about the code rather than a thing somebody
// has to remember.
//
// The landing components are NOT deleted — /how-it-works still ships them. This
// file just stopped importing them.
//
// KEPT, because it was right:
//   · THE READ IS SERVER-SIDE AND OWNER-SCOPED (listMyRuns). The browser's
//     anon/RLS client used to do it, and a stale token — e.g. after a Stripe
//     redirect — came back as an EMPTY list, so the page cheerfully reported
//     "No builds yet" to someone with a dozen films. An authError now routes to
//     the sign-in gate. Never a false-empty library.
//   · SEARCH over brand + address.
//   · A REFRESH, and a transient blip leaving the list alone.
//
// FIXED rather than kept: that last rule was written as `catch { return }`,
// which is right for a refresh of a list already on screen and wrong for the
// FIRST read — there is nothing to leave alone, so the page sat on "Loading
// runs…" forever with nothing coming. The two cases are now distinguished in
// `loadRuns`, and only the second one surfaces a retry.
//
// ADDED, for the reason the studio's own library has the shape it does: A
// LIBRARY MUST DISCRIMINATE. Thirteen filmos of one brand, all made today, are
// unfindable however well each card renders — so there is a status strip beside
// the search, and every card carries the four fields that vary between
// neighbours (see FilmoCard).
//
// The route stays /videos. It is a URL people may already hold, and renaming a
// path to match a noun breaks links to buy nothing.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { listMyRuns } from '../actions'
import { isDelivered, type Run } from '../../lib/types'
import FilmoLoader from '../components/FilmoLoader'
import LibraryShell from '../components/library/LibraryShell'
import FilterStrip, { type FilterOption } from '../components/library/FilterStrip'
import FilmoCard from '../components/library/FilmoCard'

// The three states a reader actually sorts by — not the five the database
// stores. `completed_with_warnings` is a delivered film with isolated scene
// failures: it HAS a final cut, so it belongs with the delivered ones, and
// `isDelivered` (shared with the run page and the editor) is what says so
// rather than a fifth opinion written here.
type Bucket = 'all' | 'delivered' | 'inflight' | 'failed'

function bucketOf(r: Run): Exclude<Bucket, 'all'> {
  if (isDelivered(r.status)) return 'delivered'
  if (r.status === 'failed') return 'failed'
  return 'inflight'
}

const BUCKETS: { key: Bucket; label: string; hint?: string }[] = [
  { key: 'all', label: 'All filmos' },
  { key: 'delivered', label: 'Delivered', hint: 'Finished cuts you can watch and download' },
  { key: 'inflight', label: 'In flight', hint: 'Queued at the studio, or being made right now' },
  { key: 'failed', label: 'Failed', hint: 'Builds that stopped before a cut' },
]

export default function VideosPage() {
  const { user, loading, getToken } = useAuth()
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [authError, setAuthError] = useState(false)
  const [readFailed, setReadFailed] = useState(false)
  const [q, setQ] = useState('')
  const [bucket, setBucket] = useState<Bucket>('all')

  const loadRuns = useCallback(async () => {
    setReadFailed(false)
    // AUTHORITATIVE list read SERVER-SIDE (admin client, owner-scoped) via
    // listMyRuns, so it never depends on browser-token freshness. getToken
    // falls back to the durable localStorage copy; verifyUser re-validates
    // server-side.
    const accessToken = await getToken()
    let res
    try {
      res = await listMyRuns(accessToken)
    } catch {
      // Blip. KEEP a list that is already on screen — blanking a good library
      // on a hiccup is worse than a slightly stale one, and Refresh is right
      // there. With nothing on screen there is nothing to preserve, and a
      // silent return would be a loader that never resolves.
      setRuns((prev) => { if (prev == null) setReadFailed(true); return prev })
      return
    }
    if ('authError' in res) { setAuthError(true); return }
    setAuthError(false)
    setRuns(res.runs)
  }, [getToken])

  useEffect(() => { if (user) void loadRuns() }, [user, loadRuns])

  // Search first, then status — so the count on each status pill says what
  // pressing it would actually yield from where the reader is standing, rather
  // than a total from before they started typing.
  const searched = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return runs || []
    return (runs || []).filter((r) =>
      `${r.brand || ''} ${r.company_url || ''}`.toLowerCase().includes(t))
  }, [runs, q])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: searched.length }
    for (const r of searched) {
      const b = bucketOf(r)
      c[b] = (c[b] || 0) + 1
    }
    return c
  }, [searched])

  const options = useMemo<FilterOption<Bucket>[]>(
    () => BUCKETS
      .filter((b) => b.key === 'all' || counts[b.key])
      .map((b) => ({ ...b, count: counts[b.key] || 0 })),
    [counts],
  )

  // Typing can dissolve the bucket that is selected. Fall back to All rather
  // than showing an empty grid under a pill that is no longer on the strip.
  const active: Bucket = options.some((o) => o.key === bucket) ? bucket : 'all'

  const shown = useMemo(
    () => (active === 'all' ? searched : searched.filter((r) => bucketOf(r) === active)),
    [searched, active],
  )

  let body: React.ReactNode
  if (loading) {
    // The shared loader, sized as a region inside a page that already has
    // chrome — never `fit="screen"`, which would claim a viewport this page has
    // already spent on a rail and a heading.
    body = <FilmoLoader fit="block" />
  } else if (!user || authError) {
    // Signed out, OR a stale/expired session token. A sign-in prompt only — no
    // data is queried and none is exposed.
    body = (
      <div className="lib-gate">
        <b>Sign in to see your filmos</b>
        <span>
          Your filmos live in your account. Sign in to pick up where you left off.
        </span>
        <Link className="lib-gatebtn" href="/login">Sign in</Link>
      </div>
    )
  } else if (readFailed) {
    body = (
      <div className="lib-gate">
        <b>That didn&rsquo;t load</b>
        <span>
          The studio couldn&rsquo;t be reached just now. Nothing is lost — your
          filmos are where you left them.
        </span>
        <button className="lib-gatebtn" onClick={() => void loadRuns()}>Try again</button>
      </div>
    )
  } else if (runs == null) {
    body = <FilmoLoader fit="block" />
  } else if (runs.length === 0) {
    body = (
      <div className="lib-empty">
        <b>Nothing filmed yet.</b>
        <span>
          Give Filmo a product address and it reads the site the way a first-time
          visitor would, records the pages that carry the argument, and cuts a
          film from what it actually found. Your filmos collect here.
        </span>
        <Link className="lib-emptycta" href="/?new=1">New filmo</Link>
      </div>
    )
  } else {
    body = (
      <>
        <FilterStrip
          options={options}
          value={active}
          onChange={setBucket}
          ariaLabel="Filter filmos by status"
        />
        <div className="lib-toolbar">
          <input
            className="lib-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by brand or address…"
            aria-label="Search your filmos"
          />
          <span className="lib-count">
            {shown.length} {shown.length === 1 ? 'filmo' : 'filmos'}
          </span>
          <button className="lib-refresh" onClick={() => void loadRuns()}>Refresh</button>
        </div>

        {/* A search that matches nothing is not an empty library, and a blank
            grid under a filled search box reads as a broken page. Name what
            found nothing, say how many there are in all, and offer the way
            back. */}
        {shown.length === 0 ? (
          <div className="lib-empty">
            <b>Nothing matches that search.</b>
            <span>
              Search reads the brand and the address a filmo was made from. You
              have {runs.length} filmo{runs.length === 1 ? '' : 's'} in all.
            </span>
            <button
              className="lib-emptycta"
              onClick={() => { setQ(''); setBucket('all') }}
            >
              Clear search
            </button>
          </div>
        ) : (
          <ul className="lib-grid lg">
            {shown.map((r) => <FilmoCard key={r.id} run={r} />)}
          </ul>
        )}
      </>
    )
  }

  return (
    <LibraryShell
      current="filmos"
      title="Filmos"
      lede={
        <>
          Every filmo you&rsquo;ve made, newest first — what Filmo opened,
          recorded and cut. Open one to watch it, edit it, or download the
          finished film.
        </>
      }
      context="/videos"
      getToken={getToken}
    >
      {body}
    </LibraryShell>
  )
}
