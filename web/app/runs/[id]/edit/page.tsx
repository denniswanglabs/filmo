'use client'
// In-browser video editor for a run. Loads the run (incl. the render-ready `props`
// the worker persists, and any `props_edited` from a prior save), then mounts the
// ported @remotion/player live-preview editor wired to those props. Inspector edits
// mutate props state -> the <Player> re-renders live; Save writes props_edited via
// the saveEditedProps server action. (Export/rerender + VO/music editing = Phase 3.)
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { insforge } from '../../../../lib/insforge'
import { useAuth } from '../../../../lib/auth'
import { TopBar } from '../../../components/Brand'
import { saveEditedProps, requestReRender, editViaChat } from '../../../actions'
import type { Run } from '../../../../lib/types'
import { Editor } from './_editor/Editor'

// Minimal shape we read off props for the empty-state copy + asset base.
type RunProps = { scenes?: unknown[] } & Record<string, unknown>

export default function EditRunPage() {
  const params = useParams<{ id: string }>()
  const runId = params?.id
  const router = useRouter()
  const { user, loading } = useAuth()

  const [run, setRun] = useState<Run | null>(null)
  const [notFound, setNotFound] = useState(false)
  // Bumps whenever a NEW edited_url lands (a chat/Export re-render finished). The
  // Editor passes this to the chat panel so a pending "applying…" bubble resolves
  // to "Done — updated preview on the right."
  const [editedRenderSignal, setEditedRenderSignal] = useState(0)
  const lastEditedUrl = useRef<string | null | undefined>(undefined)

  useEffect(() => {
    if (loading || !user || !runId) return
    let cancelled = false
    ;(async () => {
      // RLS scopes the anon client to rows the signed-in user owns, so this both
      // loads the run and enforces ownership.
      const { data, error } = await insforge.database
        .from('runs')
        .select()
        .eq('id', runId)
        .maybeSingle()
      if (cancelled) return
      if (error) return
      if (!data) {
        setNotFound(true)
        return
      }
      const r = data as Run
      lastEditedUrl.current = r.edited_url ?? null
      setRun(r)
    })()
    return () => {
      cancelled = true
    }
  }, [loading, user, runId])

  // Poll runs.edited_url so a chat-driven (or Export) re-render surfaces here
  // without a manual refresh. When the URL flips from null -> a value (or changes),
  // bump editedRenderSignal so the chat panel resolves its pending bubble.
  useEffect(() => {
    if (loading || !user || !runId) return
    const t = setInterval(async () => {
      const { data } = await insforge.database
        .from('runs')
        .select('edited_url')
        .eq('id', runId)
        .maybeSingle()
      const url = (data as { edited_url?: string | null } | null)?.edited_url ?? null
      if (lastEditedUrl.current === undefined) {
        lastEditedUrl.current = url
        return
      }
      if (url && url !== lastEditedUrl.current) {
        lastEditedUrl.current = url
        setEditedRenderSignal((n) => n + 1)
      }
    }, 3000)
    return () => clearInterval(t)
  }, [loading, user, runId])

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
      return saveEditedProps({ runId: run.id, userId: user.id, props })
    },
    [run, user]
  )

  // Export = persist the current edits, then enqueue a `rerender` job that produces
  // a NEW video (runs.edited_url). The worker re-renders the saved props_edited.
  const handleExport = useCallback(
    async (props: unknown) => {
      if (!run || !user) return { ok: false, error: 'not ready' }
      const saved = await saveEditedProps({ runId: run.id, userId: user.id, props })
      if (saved.ok === false) return saved
      return requestReRender({ runId: run.id, userId: user.id })
    },
    [run, user]
  )

  // Chat edit = natural-language request -> editViaChat server action (LLM
  // transforms props, saves props_edited, enqueues a re-render). The action's
  // result drives the chat bubbles; the edited_url poll above resolves the loop.
  const handleChatEdit = useCallback(
    async (message: string) => {
      if (!run || !user) return { ok: false, kind: 'error' as const, message: 'Not ready.' }
      return editViaChat({ runId: run.id, userId: user.id, message })
    },
    [run, user]
  )

  const handleBack = useCallback(() => {
    router.push(runId ? `/runs/${runId}` : '/')
  }, [router, runId])

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-400">Loading…</div>
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

  // Not-found / still-loading / no-props states keep the standard Filmo chrome.
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
            <p className="mt-10 text-slate-400">Loading run…</p>
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
      onSave={handleSave}
      onExport={handleExport}
      onChatEdit={handleChatEdit}
      editedRenderSignal={editedRenderSignal}
      onBack={handleBack}
    />
  )
}
