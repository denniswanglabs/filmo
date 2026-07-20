'use client'
// ═══════════════════════ /assets — THE PROVENANCE LEDGER ═════════════════════
//
// Everything Filmo has taken from a customer's site or made from it, browsable
// AND GROUPED UNDER THE FILM THAT PRODUCED IT.
//
// The product's whole claim is that nothing in a film is invented: every line
// comes from a page it read, every mark is one the site actually serves, every
// second of motion is real footage. A claim like that is worth exactly as much
// as it is CHECKABLE — so this page shows the raw material itself, and every
// tile walks back to the run that produced it.
//
// ── WHY GROUPS (2026-07-20) ─────────────────────────────────────────────────
// A flat wall of 260 tiles mixing page captures, marks, recordings, stills and
// films answers "what does Filmo collect" but not "what did THIS film come
// from" — and the second question is the point of a provenance ledger. So the
// material now sits under the filmo that made it: each group headed by that
// film's identity (its brand, its host, its date), newest film first, its assets
// beneath. The filter strip still narrows by kind — it now narrows WITHIN every
// group at once (a group with nothing of the selected kind drops out).
//
// Every asset belongs to exactly one of these films by construction — the server
// scopes the event read to the same runs the film rows come from — so there is
// no "unattached" group, and none is invented for a case the data cannot produce.
//
// ── WHAT WAS KEPT, BECAUSE IT WAS RIGHT ─────────────────────────────────────
//   · FILTERING BY KIND, each filter saying what the kind IS — the library
//     doubles as an explanation of what the agent actually collects.
//   · EVERY TILE LINKS TO ITS RUN, and now the group header does too.
//   · A STALE TOKEN NEVER YIELDS A FALSE-EMPTY LIBRARY, and never the sign-in
//     gate for a recoverable session: an authError is a hypothesis, and `load`
//     runs the /overview refresh-retry belt before any gate is considered.
//   · A FAILED READ is neither an empty account nor a loading one (see `load`).
//
// The route stays /assets. It is a URL people may already hold, and renaming a
// path to match a noun breaks links to buy nothing.
import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '../../lib/auth'
import { ensureFreshAccessToken } from '../../lib/insforge'
import { listAssets, type AssetKind, type AssetGroup } from '../actions'
import FilmoLoader from '../components/FilmoLoader'
import LibraryShell from '../components/library/LibraryShell'
import FilterStrip, { type FilterOption } from '../components/library/FilterStrip'
import AssetGroupSection from '../components/library/AssetGroupSection'

type Kind = AssetKind | 'all'

// Type names are the user's words for the thing, not the pipeline's event
// kinds — "Page capture", not "read.page". Naming what each kind IS is what
// makes the strip an explanation rather than a set of switches.
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
  const [groups, setGroups] = useState<AssetGroup[] | null>(null)
  const [authError, setAuthError] = useState(false)
  // A read that FAILED is not an account that is empty, and it is not one that
  // is still loading either. Only set when there is nothing already on screen.
  const [readFailed, setReadFailed] = useState(false)
  const [kind, setKind] = useState<Kind>('all')

  const load = useCallback(async () => {
    setReadFailed(false)
    const read = async () => listAssets(await getToken())
    const denied = (r: Awaited<ReturnType<typeof read>>) => 'authError' in r
    try {
      let res = await read()
      // ONE STALE 401 IS NOT A SIGNOUT — the /overview belt, adopted here
      // (2026-07-20). The access token can expire mid-session while a valid
      // refresh token still sits in localStorage; the read carries the dead
      // bearer and verifyUser answers a clean 401. So before the gate is even
      // considered: force ONE refresh (the server outranks the client's clock)
      // and retry the read ONCE on the fresh token. The invariant this
      // establishes: a user holding a valid refresh token never sees the
      // sign-in gate — they see their assets, or a "try again", never the door.
      if (denied(res)) {
        const freshness = await ensureFreshAccessToken({ force: true })
        if (freshness === 'ok') res = await read()
        if (denied(res)) {
          if (freshness === 'unavailable') {
            // The auth service itself was unreachable: the session is UNKNOWN,
            // not dead — a blip with a retry, never the gate. Treated exactly
            // like a thrown read below: KEEP a list already on screen (Refresh
            // is right there), and only say "try again" with nothing to keep.
            setGroups((prev) => { if (prev == null) setReadFailed(true); return prev })
            return
          }
          // Definitive: the refresh credential is gone/revoked ('signed-out'),
          // or a token minted seconds ago was still rejected. The gate is honest.
          setAuthError(true)
          return
        }
      }
      if ('authError' in res) return // unreachable after the block; narrows below
      setAuthError(false)
      setGroups(res.groups)
    } catch {
      // A thrown server action is a network/timeout blip. If a library is
      // already on screen, KEEP it — blanking a good list on a hiccup is worse
      // than a stale one, and Refresh is right there. If there is nothing on
      // screen, say so, because the alternative is a spinner that never ends.
      setGroups((prev) => { if (prev == null) setReadFailed(true); return prev })
    }
  }, [getToken])

  // KEYED ON THE USER'S ID, NEVER THE USER OBJECT — same reason as /videos, which
  // carries the full note. AuthProvider calls setUser twice with two freshly built
  // objects (optimistic restore, then network reconcile), so depending on `user`
  // re-ran this read for a person who never changed; Next.js serializes server
  // actions, so the duplicates queued end-to-end instead of overlapping.
  const userId = user?.id
  useEffect(() => { if (userId) void load() }, [userId, load])

  // Kind counts are over EVERY asset in every group — the strip is a census of
  // the whole library, not of one film.
  const allAssets = useMemo(() => (groups || []).flatMap((g) => g.assets), [groups])
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: allAssets.length }
    for (const a of allAssets) c[a.kind] = (c[a.kind] || 0) + 1
    return c
  }, [allAssets])

  // A filter that would return nothing is a dead end, so it is not offered.
  const options = useMemo<FilterOption<Kind>[]>(
    () => KINDS
      .filter((k) => k.key === 'all' || counts[k.key])
      .map((k) => ({ ...k, count: counts[k.key] || 0 })),
    [counts],
  )

  // A filter can survive the disappearance of the thing it filtered (a refresh
  // that returns fewer kinds). Fall back to All rather than showing an empty
  // page under a pill that no longer exists.
  const active: Kind = options.some((o) => o.key === kind) ? kind : 'all'

  // Apply the active filter WITHIN each group, and drop a group that has nothing
  // of the selected kind — a header with no tiles beneath is a dead row.
  const shownGroups = useMemo(
    () => (groups || [])
      .map((g) => ({ group: g, assets: active === 'all' ? g.assets : g.assets.filter((a) => a.kind === active) }))
      .filter((x) => x.assets.length > 0),
    [groups, active],
  )
  const shownCount = useMemo(
    () => shownGroups.reduce((n, x) => n + x.assets.length, 0),
    [shownGroups],
  )

  let body: React.ReactNode
  if (loading) {
    // The shared loader, sized as a region inside a page that already has
    // chrome — never `fit="screen"`, which would claim a viewport this page has
    // already spent on a rail and a heading.
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
  } else if (groups == null) {
    body = <FilmoLoader fit="block" />
  } else if (groups.length === 0) {
    body = (
      <div className="lib-empty">
        <b>Nothing captured yet.</b>
        <span>
          Make a filmo and everything Filmo reads, records and cuts on the way
          collects here — the pages, the marks, the footage, every scene.
        </span>
        <Link className="lib-emptycta" href="/new">New filmo</Link>
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
            {shownCount} {shownCount === 1 ? 'asset' : 'assets'} ·{' '}
            {shownGroups.length} {shownGroups.length === 1 ? 'filmo' : 'filmos'}
          </span>
          <button className="lib-refresh" onClick={() => void load()}>Refresh</button>
        </div>

        {shownGroups.map(({ group, assets }) => (
          <AssetGroupSection key={group.runId} group={group} assets={assets} />
        ))}
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
          it cut. Grouped under the filmo that produced it; nothing here comes
          from anywhere else.
        </>
      }
      context="/assets"
      getToken={getToken}
    >
      {body}
    </LibraryShell>
  )
}
