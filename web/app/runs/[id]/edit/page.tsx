'use client'
// In-browser video editor for a run. Loads the run (incl. the render-ready `props`
// the worker persists, and any `props_edited` from a prior save), then mounts the
// ported @remotion/player live-preview editor wired to those props. Inspector edits
// mutate props state -> the <Player> re-renders live; Save writes props_edited via
// the saveEditedProps server action. (Export/rerender + VO/music editing = Phase 3.)
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '../../../../lib/auth'
import { TopBar } from '../../../components/Brand'
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

  const [run, setRun] = useState<Run | null>(null)
  const [notFound, setNotFound] = useState(false)

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

  // Auth resolving — a continuation of this route's loading.tsx, same pixels.
  if (loading) {
    return <FilmoLoader ground={GROUND_LIGHT} />
  }

  if (!user) {
    return (
      <>
        <TopBar />
        <main className="mx-auto max-w-3xl px-5 pb-24 pt-8">
          <p className="mt-10 text-slate-500">Please sign in to edit this video.</p>
        </main>
      </>
    )
  }

  // Signed in, nothing wrong, the run row just isn't here yet — hold the boot
  // screen rather than dropping to chrome + "Loading run…" in grey. Same
  // treatment (and same reasoning) as the run route this editor hangs off.
  if (!run && !notFound) {
    return <FilmoLoader ground={GROUND_LIGHT} />
  }

  // Not-found / no-props states keep the standard Filmo chrome — an error you
  // have to navigate away from needs a nav bar to navigate with.
  if (notFound || !run || !editorProps) {
    return (
      <>
        <TopBar />
        <main className="mx-auto max-w-3xl px-5 pb-24 pt-8">
          <Link href={runId ? `/runs/${runId}` : '/'} className="text-sm text-slate-400 transition hover:text-ink">
            ← Back to build
          </Link>
          {notFound ? (
            <p className="mt-10 text-slate-500">This run could not be found.</p>
          ) : !run ? (
            // Unreachable (the early return above owns this condition); kept
            // because it narrows `run` for the branch below, and a loader is
            // what it should show if it ever did paint.
            <FilmoLoader ground={GROUND_LIGHT} fit="block" />
          ) : (
            <div className="mt-5">
              <h1 className="text-2xl font-semibold tracking-tight text-ink">
                Editor — {run.brand || run.company_url}
              </h1>
              <p className="mt-1 text-slate-500">{run.goal || 'Brand video'}</p>
              <div className="mt-6 rounded-2xl border border-[#E6EAF0] bg-[#F8FAFF] px-5 py-8">
                <p className="text-sm font-semibold uppercase tracking-wide text-amber">Nothing to edit yet</p>
                <p className="mt-2 text-ink">
                  No render props are saved for this run yet. New builds persist them
                  automatically, then the live editor opens here.
                </p>
              </div>
            </div>
          )}
        </main>
      </>
    )
  }

  // Props loaded — mount the live editor (its own full-bleed chrome, scoped theme).
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
