'use client'
// In-browser video editor for a run. Loads the run (incl. the render-ready `props`
// the worker persists, and any `props_edited` from a prior save), then mounts the
// ported @remotion/player live-preview editor wired to those props. Inspector edits
// mutate props state -> the <Player> re-renders live; Save writes props_edited via
// the saveEditedProps server action. (Export/rerender + VO/music editing = Phase 3.)
//
// ── THE CHROME (2026-07-20) ──────────────────────────────────────────────────
// The editor itself is untouched — it draws its own full-bleed, scoped chrome
// (`.ws-editor-root`, white canvas). What changed is everything AROUND it: the
// sign-in and not-found states used to wear `TopBar` (the old white marketing
// header); they now wear the app's rail on the editor's own white ground, so
// arriving here is branded loader → editor, and even the error states belong
// to the same product as the rest of the app. Nothing lights on the rail — the
// editor is not one of its entries (same `current="none"` honesty as
// /analytics and the run page).
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { useAuth } from '../../../../lib/auth'
import OverviewRail from '../../../components/overview/OverviewRail'
import FeedbackModal from '../FeedbackModal'
import FilmoLoader, { GROUND_LIGHT } from '../../../components/FilmoLoader'
import { saveEditedProps, requestReRender, getRunForViewer } from '../../../actions'
import { isDelivered, type Run } from '../../../../lib/types'
import { Editor } from './_editor/Editor'

// Minimal shape we read off props for the empty-state copy + asset base.
type RunProps = { scenes?: unknown[] } & Record<string, unknown>

export default function EditRunPage() {
  const params = useParams<{ id: string }>()
  const runId = params?.id
  const router = useRouter()
  const { user, loading, getToken } = useAuth()

  const [mounted, setMounted] = useState(false)
  const [fbOpen, setFbOpen] = useState(false)
  const [run, setRun] = useState<Run | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => setMounted(true), [])

  useEffect(() => {
    if (loading || !user || !runId) return
    let cancelled = false
    ;(async () => {
      // AUTHORITATIVE read SERVER-SIDE (admin client, owner-scoped) via getRunForViewer,
      // so the editor never depends on browser-token freshness — the same fix as the run
      // page (a stale ~15-min session token used to make the RLS read return EMPTY and
      // strand the editor on "could not be found"). The server action verifies the token
      // and enforces ownership; a transient/thrown error just leaves the editor on its
      // loading state (a real 4xx-equivalent maps to notFound/authError below).
      const accessToken = await getToken()
      let res
      try {
        res = await getRunForViewer({ runId, accessToken })
      } catch {
        return // transient blip — leave on loading; no false not-found
      }
      if (cancelled) return
      // An expired/invalid token strands the load (no run row to show); we don't have a
      // re-auth UI on the editor, so fall through to the not-found chrome (the run page,
      // which the user reaches first, owns the "sign in again" prompt).
      if ('authError' in res || 'notFound' in res) {
        setNotFound(true)
        return
      }
      setRun(res.run)
    })()
    return () => {
      cancelled = true
    }
  }, [loading, user, runId, getToken])

  // Prefer a saved edit (props_edited) over the clean props so re-opening the editor
  // resumes the last save; fall back to the original render-ready props.
  const editorProps = useMemo<RunProps | null>(() => {
    const edited = (run?.props_edited ?? null) as RunProps | null
    const clean = (run?.props ?? null) as RunProps | null
    const chosen = edited && Array.isArray(edited.scenes) ? edited : clean
    if (!chosen || typeof chosen !== 'object') return null

    // Seed editable VO copy. The render props.json does NOT carry VO text — that
    // lives in plan.voiceover.beats (durable in runs.plan). Merge those beats into
    // props.voiceover.beats (keyed by scene_id) so the inspector's VO panel can edit
    // them; on Export the worker reads props.voiceover (+ dirty) to re-synthesize.
    // If a prior save already carries an (edited) voiceover block, keep it.
    const out = { ...chosen } as RunProps
    const existingVo = (chosen as { voiceover?: unknown }).voiceover as
      | { beats?: Array<{ scene_id?: string; text?: string }>; dirty?: boolean }
      | undefined
    if (!existingVo || !Array.isArray(existingVo.beats)) {
      const plan = (run?.plan ?? null) as { voiceover?: { beats?: Array<{ scene_id?: string; text?: string }> } } | null
      const planBeats = plan?.voiceover?.beats
      if (Array.isArray(planBeats) && planBeats.length) {
        ;(out as { voiceover?: unknown }).voiceover = {
          beats: planBeats.map((b) => ({ scene_id: b.scene_id, text: b.text || '' })),
          dirty: false,
        }
      }
    }
    return out
  }, [run])

  // Asset base: per-run assets live (when uploaded) under the InsForge `walk-videos`
  // bucket namespaced by run_key. The preview prepends this to public-relative asset
  // names so they resolve to the bucket. (Today the bucket holds only final.mp4 —
  // per-scene screenshot/VO/music upload is Phase-3 worker work — so those assets
  // 404 gracefully; text/layout/motion still render from the real props.)
  const assetBaseUrl = useMemo(() => {
    const insforgeUrl = process.env.NEXT_PUBLIC_INSFORGE_URL
    if (!insforgeUrl || !run?.run_key) return undefined
    return `${insforgeUrl.replace(/\/+$/, '')}/api/storage/buckets/walk-videos/objects/${run.run_key}`
  }, [run])

  const handleSave = useCallback(
    async (props: unknown) => {
      if (!run || !user) return { ok: false, error: 'not ready' }
      const accessToken = await getToken()
      if (!accessToken) return { ok: false, error: 'not signed in' }
      return saveEditedProps({ runId: run.id, accessToken, props })
    },
    [run, user, getToken]
  )

  // Export = persist the current edits, then enqueue a `rerender` job that produces
  // a NEW video (runs.edited_url). The worker re-renders the saved props_edited.
  const handleExport = useCallback(
    async (props: unknown) => {
      if (!run || !user) return { ok: false, error: 'not ready' }
      const accessToken = await getToken()
      if (!accessToken) return { ok: false, error: 'not signed in' }
      const saved = await saveEditedProps({ runId: run.id, accessToken, props })
      if (saved.ok === false) return saved
      return requestReRender({ runId: run.id, accessToken })
    },
    [run, user, getToken]
  )

  const handleBack = useCallback(() => {
    router.push(runId ? `/runs/${runId}` : '/')
  }, [router, runId])

  // Auth resolving (or no document yet to portal the chrome into) — a
  // continuation of this route's loading.tsx, same pixels.
  if (loading || !mounted) {
    return <FilmoLoader ground={GROUND_LIGHT} />
  }

  // Signed in, nothing wrong, the run row just isn't here yet — hold the boot
  // screen rather than dropping to chrome + "Loading run…" in grey. Same
  // treatment (and same reasoning) as the run route this editor hangs off.
  if (user && !run && !notFound) {
    return <FilmoLoader ground={GROUND_LIGHT} />
  }

  // Props loaded — mount the live editor (its own full-bleed chrome, scoped theme).
  if (user && run && !notFound && editorProps) {
    return (
      <Editor
        runId={run.id}
        initialProps={editorProps}
        brand={run.brand || run.company_url}
        goal={run.goal || undefined}
        assetBaseUrl={assetBaseUrl}
        musicAssetName={run.run_key ? `music-${run.run_key}.mp3` : undefined}
        downloadUrl={isDelivered(run.status) && run.final_url ? `/api/runs/${run.id}/download` : undefined}
        onSave={handleSave}
        onExport={handleExport}
        onBack={handleBack}
      />
    )
  }

  // ── THE STATES AROUND THE EDITOR ────────────────────────────────────────────
  // Sign-in, not-found and nothing-to-edit keep real chrome — an error you have
  // to navigate away from needs navigation to leave with, and that is the rail
  // now. Ground is the editor's own white so the route's loader, these states
  // and the editor itself are one surface.
  let body: React.ReactNode
  if (!user) {
    body = (
      <div className="ed-gate">
        <b>Please sign in to edit this video.</b>
        <Link href="/login" className="ed-gatebtn">
          Sign in
        </Link>
      </div>
    )
  } else if (notFound) {
    body = (
      <div className="ed-gate">
        <b>This run could not be found.</b>
        <Link href={runId ? `/runs/${runId}` : '/videos'} className="ed-gatebtn">
          Back to the build
        </Link>
      </div>
    )
  } else if (run) {
    body = (
      <div>
        <h1 className="ed-h1">Editor — {run.brand || run.company_url}</h1>
        <p className="ed-sub">{run.goal || 'Brand video'}</p>
        <div className="ed-empty">
          <b>Nothing to edit yet</b>
          <span>
            No render props are saved for this run yet. New builds persist them
            automatically, then the live editor opens here.
          </span>
          <Link href={runId ? `/runs/${runId}` : '/videos'} className="ed-gatebtn">
            Back to the build
          </Link>
        </div>
      </div>
    )
  } else {
    // Unreachable (the early returns above own every other combination); kept
    // because a loader is what this must show if it ever did paint.
    body = <FilmoLoader ground={GROUND_LIGHT} fit="block" />
  }

  return createPortal(
    <div className="ed-root">
      <OverviewRail current="none" getToken={getToken} onFeedback={() => setFbOpen(true)} />

      <main className="ed-stage">
        <div className="ed-inner">{body}</div>
      </main>

      <FeedbackModal
        open={fbOpen}
        onClose={() => setFbOpen(false)}
        getToken={getToken}
        context={runId ? `/runs/${runId}/edit` : '/runs'}
      />

      <style>{`
        /* The editor's canvas is white (.ws-editor-root --bg:#FFFFFF); these
           wrapper states share it so loader → state → editor never flashes. */
        .ed-root { position:fixed; inset:0; display:flex; background:#FFFFFF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        .ed-stage { flex:1 1 0; min-width:0; min-height:0; overflow-y:auto;
          overflow-x:hidden; }
        .ed-inner { max-width:768px; margin:0 auto; padding:38px 24px 64px; }

        .ed-h1 { margin:0; font-size:24px; font-weight:600;
          letter-spacing:-.02em; color:#1B1B1A; }
        .ed-sub { margin:5px 0 0; font-size:14px; color:#8A8A86; }

        .ed-gate, .ed-empty { background:#fff; border:1px solid #E6E6E3;
          border-radius:14px; padding:26px; display:flex; flex-direction:column;
          gap:8px; align-items:flex-start; max-width:520px; }
        .ed-gate { margin-top:24px; }
        .ed-empty { margin-top:22px; }
        .ed-gate b, .ed-empty b { font-size:15px; font-weight:650; color:#1B1B1A; }
        .ed-gate span, .ed-empty span { font-size:13.5px; line-height:1.55;
          color:#6E6E6A; }
        .ed-gatebtn { margin-top:8px; display:inline-flex; align-items:center;
          justify-content:center; border:1px solid #1B1B1A; background:#1B1B1A;
          color:#fff; border-radius:99px; padding:9px 20px;
          font:13px/1 Inter,-apple-system,sans-serif; text-decoration:none; }
        .ed-gatebtn:hover { background:#000; border-color:#000; }
        .ed-gatebtn:focus-visible { outline:2px solid #3B82F6; outline-offset:3px; }

        @media (max-width:760px) { .ed-inner { padding:26px 16px 48px; } }
      `}</style>
    </div>,
    document.body,
  )
}
