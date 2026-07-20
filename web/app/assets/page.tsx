'use client'
// ═══════════════════════ /assets — THE PROVENANCE LEDGER ═════════════════════
//
// Everything Filmo has taken from a customer's site or made from it, browsable.
//
// The product's whole claim is that nothing in a film is invented: every line
// comes from a page it read, every mark is one the site actually serves, every
// second of motion is real footage. A claim like that is worth exactly as much
// as it is CHECKABLE — so this page shows the raw material itself, and every
// tile walks back to the run that produced it.
//
// ── WHAT CHANGED, AND WHAT DELIBERATELY DID NOT (2026-07-19) ────────────────
// The page was wearing the old blue landing chrome — FloatingNav, SiteFooter,
// LandingBackdrop — which is the marketing shell, not the product's. It now
// wears the studio ground and the product's rail, like the Overview and like
// its sibling /videos. Those landing components are NOT deleted; /how-it-works
// still ships them. This file just stopped importing them.
//
// Three behaviours from the first version were kept because they were right:
//   · FILTERING BY KIND, and each filter saying what the kind IS — the library
//     doubles as an explanation of what the agent actually collects.
//   · EVERY TILE LINKS TO ITS RUN. Provenance is the point (see AssetTile).
//   · A STALE TOKEN PROMPTS SIGN-IN, never a false-empty library.
//
// One thing was fixed rather than kept: the old read swallowed a thrown server
// action whole (`catch { return }`), which on a FIRST load left the page saying
// "Loading assets…" forever with nothing on the way. A failed read is not an
// empty account and it is not a loading one — see `load` below.
//
// The route stays /assets. It is a URL people may already hold, and renaming a
// path to match a noun breaks links to buy nothing.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { listAssets, type AssetKind, type AssetRow } from '../actions'
import FilmoLoader from '../components/FilmoLoader'
import LibraryShell from '../components/library/LibraryShell'
import FilterStrip, { type FilterOption } from '../components/library/FilterStrip'
import AssetTile from '../components/library/AssetTile'

type Kind = AssetKind | 'all'

// Type names are the user's words for the thing, not the pipeline's event
// kinds — "Page capture", not "read.page". Preserved verbatim from the first
// version of this page, hints included: naming what each kind IS is what makes
// the strip an explanation rather than a set of switches.
const KINDS: { key: Kind; label: string; hint?: string }[] = [
  { key: 'all', label: 'All assets' },
  { key: 'film', label: 'Films', hint: 'The finished cut' },
  { key: 'recording', label: 'Recordings', hint: 'Real screen footage' },
  { key: 'capture', label: 'Page captures', hint: 'Pages Filmo read' },
  { key: 'scene', label: 'Scene stills', hint: 'Frames from each beat' },
  { key: 'mark', label: 'Brand marks', hint: 'Logos from the site' },
]

export default function AssetsPage() {
  const { user, loading, getToken } = useAuth()
  const [assets, setAssets] = useState<AssetRow[] | null>(null)
  const [authError, setAuthError] = useState(false)
  // A read that FAILED is not an account that is empty, and it is not one that
  // is still loading either. Only set when there is nothing already on screen.
  const [readFailed, setReadFailed] = useState(false)
  const [kind, setKind] = useState<Kind>('all')

  const load = useCallback(async () => {
    setReadFailed(false)
    const token = await getToken()
    let res
    try {
      res = await listAssets(token)
    } catch {
      // A thrown server action is a network/timeout blip. If a library is
      // already on screen, KEEP it — blanking a good list on a hiccup is worse
      // than a stale one, and Refresh is right there. If there is nothing on
      // screen, say so, because the alternative is a spinner that never ends.
      setAssets((prev) => { if (prev == null) setReadFailed(true); return prev })
      return
    }
    // Expired/invalid token → the sign-in gate, never a false-empty library.
    if ('authError' in res) { setAuthError(true); return }
    setAuthError(false)
    setAssets(res.assets)
  }, [getToken])

  useEffect(() => { if (user) void load() }, [user, load])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: assets?.length || 0 }
    for (const a of assets || []) c[a.kind] = (c[a.kind] || 0) + 1
    return c
  }, [assets])

  // A filter that would return nothing is a dead end, so it is not offered —
  // the first version's rule, kept.
  const options = useMemo<FilterOption<Kind>[]>(
    () => KINDS
      .filter((k) => k.key === 'all' || counts[k.key])
      .map((k) => ({ ...k, count: counts[k.key] || 0 })),
    [counts],
  )

  // A filter can survive the disappearance of the thing it filtered (a refresh
  // that returns fewer kinds). Fall back to All rather than showing an empty
  // grid under a pill that no longer exists.
  const active: Kind = options.some((o) => o.key === kind) ? kind : 'all'

  const shown = useMemo(
    () => (assets || []).filter((a) => active === 'all' || a.kind === active),
    [assets, active],
  )

  let body: React.ReactNode
  if (loading) {
    // The shared loader, sized as a region inside a page that already has
    // chrome — never `fit="screen"`, which would claim a viewport this page has
    // already spent on a rail and a heading. The ground is left at its default
    // (#F1F1EF), which is now this surface's ground too.
    body = <FilmoLoader fit="block" />
  } else if (!user || authError) {
    // No redirect. Someone who typed this URL gets the door, not a bounce.
    body = (
      <div className="lib-gate">
        <b>Sign in to see your assets</b>
        <span>
          Everything Filmo captured for you lives in your account, alongside the
          filmos made from it.
        </span>
        <Link className="lib-gatebtn" href="/login">Sign in</Link>
      </div>
    )
  } else if (readFailed) {
    body = (
      <div className="lib-gate">
        <b>That didn&rsquo;t load</b>
        <span>
          The studio couldn&rsquo;t be reached just now. Nothing is lost — every
          asset is where you left it.
        </span>
        <button className="lib-gatebtn" onClick={() => void load()}>Try again</button>
      </div>
    )
  } else if (assets == null) {
    body = <FilmoLoader fit="block" />
  } else if (assets.length === 0) {
    body = (
      <div className="lib-empty">
        <b>Nothing captured yet.</b>
        <span>
          Make a filmo and everything Filmo reads, records and cuts on the way
          collects here — the pages, the marks, the footage, every scene.
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
          onChange={setKind}
          ariaLabel="Filter assets by kind"
        />
        <div className="lib-toolbar">
          <span className="lib-count">
            {shown.length} {shown.length === 1 ? 'asset' : 'assets'}
          </span>
          <button className="lib-refresh" onClick={() => void load()}>Refresh</button>
        </div>
        <ul className="lib-grid">
          {shown.map((a) => <AssetTile key={a.id} asset={a} />)}
        </ul>
      </>
    )
  }

  return (
    <LibraryShell
      current="assets"
      title="Assets"
      lede={
        <>
          Everything Filmo took from your site, or made from it — the pages it
          read, the marks it captured, the footage it recorded, and every scene
          it cut. Nothing in a filmo comes from anywhere else.
        </>
      }
      context="/assets"
      getToken={getToken}
    >
      {body}
    </LibraryShell>
  )
}
