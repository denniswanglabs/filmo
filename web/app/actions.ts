'use server'
import { adminClient } from '../lib/insforge'

// ─────────────────────────── In-browser editor: save ───────────────────────────
// Persist the editor's edited props into runs.props_edited (a separate jsonb column
// from the clean, worker-generated `props`, so "revert to original" stays possible).
// Admin client bypasses RLS — but we scope the write to a single run id (and require
// a signed-in owner via `userId`, verified against the row) so a user can only save
// edits to a run they own. The clean `props` column is never touched here.
export async function saveEditedProps(input: {
  runId: string
  userId: string
  props: unknown
}): Promise<{ ok: boolean; error?: string }> {
  if (!input.runId || !input.userId) return { ok: false, error: 'missing runId/userId' }
  if (input.props == null || typeof input.props !== 'object') {
    return { ok: false, error: 'invalid props' }
  }
  const db = adminClient()
  // Ownership check: the admin client ignores RLS, so verify the run belongs to the
  // caller before writing (defense-in-depth — the page already RLS-loads the run).
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, error: 'read: ' + JSON.stringify(readErr) }
  if (!run) return { ok: false, error: 'run not found' }
  if ((run as { user_id?: string }).user_id !== input.userId) {
    return { ok: false, error: 'not the run owner' }
  }
  const { error } = await db.database
    .from('runs')
    .update({ props_edited: input.props })
    .eq('id', input.runId)
  if (error) return { ok: false, error: JSON.stringify(error) }
  return { ok: true }
}

// Create a build the way the worker expects: a `runs` row (status=queued) + a `jobs`
// row (status=queued). The Railway worker's claim_next_job picks it up. user_id comes
// from the signed-in user (the run owner). Returns the new run id + key.
export async function createBuild(input: {
  userId: string
  url: string
  goal?: string
  emphasis?: string
  quality?: 'standard' | 'premium'
  brain?: string
  mode?: 'mock' | 'real'
  // Opt-in HUMAN payment: 'auto' (default) lets the worker auto-resolve payment
  // (PRODUCER_SIMULATE_PAID); 'human' creates a REAL Stripe TEST checkout the user
  // must pay (test card 4242) before the build proceeds. Only the payment becomes
  // real — the render stays $0 mock.
  payMode?: 'auto' | 'human'
}) {
  const db = adminClient()
  const runKey = `web-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
  const brand = input.url.replace(/^https?:\/\//, '').replace(/\/.*$/, '')
  const quality = input.quality || 'standard'
  const brain = input.brain || 'super-free'
  const mode = input.mode || 'mock'
  const payMode = input.payMode || 'auto'
  const goal = input.goal || 'A 30-second brand explainer'

  const { data: runs, error: runErr } = await db.database
    .from('runs')
    .insert([{
      user_id: input.userId, run_key: runKey, brand, company_url: input.url,
      goal, emphasis: input.emphasis || null, quality, brain, mode, status: 'queued',
    }])
    .select()
  if (runErr) throw new Error('runs.insert: ' + JSON.stringify(runErr))
  const runId = runs![0].id

  const params = { company_url: input.url, goal, emphasis: input.emphasis || '', quality, brain, mode, pay_mode: payMode, run_key: runKey, duration: 30 }
  const { error: jobErr } = await db.database.from('jobs').insert([{ run_id: runId, status: 'queued', params }])
  if (jobErr) throw new Error('jobs.insert: ' + JSON.stringify(jobErr))

  return { runId, runKey }
}

// ─────────────────────── Editor: Export → re-render job ───────────────────────
// Enqueue a `rerender` job: the worker re-renders the run's saved props_edited into
// a NEW video (runs.edited_url) without re-running capture/plan/price. Mirrors
// createBuild's insert shape, but reuses the EXISTING run row (no new run) and tags
// the job type 'rerender'. Ownership is verified against the run before enqueueing.
export async function requestReRender(input: {
  runId: string
  userId: string
}): Promise<{ ok: boolean; error?: string }> {
  if (!input.runId || !input.userId) return { ok: false, error: 'missing runId/userId' }
  const db = adminClient()
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id, run_key, props, props_edited')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, error: 'read: ' + JSON.stringify(readErr) }
  if (!run) return { ok: false, error: 'run not found' }
  const r = run as { user_id?: string; run_key?: string; props?: unknown; props_edited?: unknown }
  if (r.user_id !== input.userId) return { ok: false, error: 'not the run owner' }
  // Need SOMETHING to render: a saved edit, or the clean props as a fallback.
  const hasProps =
    (r.props_edited && typeof r.props_edited === 'object') ||
    (r.props && typeof r.props === 'object')
  if (!hasProps) return { ok: false, error: 'no props to re-render' }

  // Avoid stacking duplicate pending rerender jobs for the same run.
  const { data: pending } = await db.database
    .from('jobs')
    .select('id, status, type')
    .eq('run_id', input.runId)
    .eq('type', 'rerender')
    .in('status', ['queued', 'claimed'])
  if (pending && pending.length > 0) {
    return { ok: true } // a rerender is already in flight; treat as success (idempotent)
  }

  const params = { run_key: r.run_key, from: 'props_edited' }
  const { error: jobErr } = await db.database
    .from('jobs')
    .insert([{ run_id: input.runId, type: 'rerender', status: 'queued', params }])
  if (jobErr) return { ok: false, error: 'jobs.insert: ' + JSON.stringify(jobErr) }
  // Clear the previous edited_url so the run page shows "rendering" until the new one lands.
  await db.database.from('runs').update({ edited_url: null }).eq('id', input.runId)
  return { ok: true }
}

// ───────────────────────── Chat-driven editor: editViaChat ────────────────────
// Natural-language edit loop for the Hera-style chat editor. The user types a
// plain request ("make the title bigger", "change the headline to X", "make scene
// 2 longer", "more energetic"). This action:
//   1. loads the run's current editable props (props_edited ?? props),
//   2. asks an LLM (OpenRouter, same OPENROUTER_API_KEY the pipeline uses) to
//      transform the props JSON per the request, returning the FULL updated props
//      in the SAME schema (only changed where the request implies),
//   3. validates the returned JSON is a well-formed props object,
//   4. saveEditedProps(updatedProps) then enqueues a rerender (requestReRender).
// The run page already polls runs.edited_url, so when the re-render lands the chat
// resolves to "Done". Degrades gracefully (returns ok:false + a human message) if
// the key is missing, the LLM errors, or the output isn't valid props — never
// throws back to the client.

const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
// A capable, JSON-reliable default. Override via OPENROUTER_EDIT_MODEL if desired.
const DEFAULT_EDIT_MODEL = 'nousresearch/hermes-3-llama-3.1-405b'

// Whitelist of top-level keys the chat editor is allowed to touch. Anything outside
// this set in the LLM output is dropped (we keep the original value), so the model
// can't corrupt asset paths, fps, ids, etc. Scene-level edits go through `scenes`.
const EDITABLE_TOP_KEYS = new Set(['scenes', 'theme', 'total_frames', 'music_path', 'music_level', 'voiceover'])

type ChatProps = { scenes?: unknown[] } & Record<string, unknown>

// Defensive timeline guard. The chat model is *asked* to shift later scenes (and
// total_frames) when one scene is resized, but nothing enforced it — a missed shift
// would overlap scenes or leave gaps and silently ship a broken render. This re-lays
// scenes end-to-end in their existing order, preserving each scene's (possibly newly
// edited) DURATION, and recomputes total_frames. It is a no-op when the timeline is
// already contiguous, so correct LLM output and non-timing edits pass through untouched.
// Safe because scenes carry no absolute internal frame refs — archetype animation is
// relative to each scene's own [in_frame,out_frame] window.
function normalizeTimeline(props: ChatProps): ChatProps {
  const scenes = Array.isArray(props.scenes) ? props.scenes : []
  if (scenes.length === 0) return props
  const first = scenes[0] as Record<string, unknown>
  let cursor = Number(first.in_frame)
  if (!Number.isFinite(cursor) || cursor < 0) cursor = 0
  let changed = false
  const relaid = scenes.map((s) => {
    const sc = s as Record<string, unknown>
    const inF = Number(sc.in_frame)
    const outF = Number(sc.out_frame)
    let dur = Number.isFinite(inF) && Number.isFinite(outF) ? outF - inF : 0
    if (!Number.isFinite(dur) || dur < 1) dur = 1 // never a zero/negative-length scene
    const newIn = cursor
    const newOut = cursor + dur
    if (newIn !== inF || newOut !== outF) changed = true
    cursor = newOut
    return { ...sc, in_frame: newIn, out_frame: newOut }
  })
  if (!changed && Number(props.total_frames) === cursor) return props
  return { ...props, scenes: relaid, total_frames: cursor }
}

// Validate the LLM output is a structurally-sound props object: an object with a
// non-empty scenes array whose every scene keeps an id + numeric frame bounds.
// Returns the SANITIZED props (merged onto the original so untouched keys survive)
// or null when the shape is unusable.
function sanitizeProps(original: ChatProps, candidate: unknown): ChatProps | null {
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return null
  const c = candidate as ChatProps
  if (!Array.isArray(c.scenes) || c.scenes.length === 0) return null
  // Scene count must match — the editor edits existing scenes, never add/drop here.
  const origScenes = Array.isArray(original.scenes) ? original.scenes : []
  if (c.scenes.length !== origScenes.length) return null

  const scenes = c.scenes.map((s, i) => {
    const orig = (origScenes[i] || {}) as Record<string, unknown>
    if (!s || typeof s !== 'object') return orig
    const sc = s as Record<string, unknown>
    // Preserve identity + archetype from the original (never let the LLM rename them).
    const inF = Number(sc.in_frame ?? orig.in_frame ?? 0)
    const outF = Number(sc.out_frame ?? orig.out_frame ?? 0)
    return {
      ...orig,
      ...sc,
      id: orig.id ?? sc.id,
      archetype: orig.archetype ?? sc.archetype,
      in_frame: Number.isFinite(inF) ? inF : (orig.in_frame as number) ?? 0,
      out_frame: Number.isFinite(outF) ? outF : (orig.out_frame as number) ?? 0,
      cues: orig.cues ?? sc.cues ?? [],
    }
  })

  // Start from the original so non-editable keys (fps, lang, audio_path, ids,
  // assetBaseUrl, …) survive untouched; overlay only whitelisted keys from the LLM.
  const out: ChatProps = { ...original, scenes }
  for (const k of EDITABLE_TOP_KEYS) {
    if (k === 'scenes') continue
    if (k in c && c[k] != null) out[k] = c[k]
  }
  // Guarantee a contiguous, non-overlapping timeline even if the model botched the
  // frame arithmetic on a timing edit. No-op for clean/non-timing output.
  return normalizeTimeline(out)
}

// A compact view of the props we hand the model: scene id/archetype/timing +
// editable copy + geometry, plus theme + total_frames. Keeps the prompt small and
// steers the model toward the keys it should change.
function describeForLLM(props: ChatProps) {
  return JSON.stringify(props, null, 0)
}

export async function editViaChat(input: {
  runId: string
  userId: string
  message: string
}): Promise<{
  ok: boolean
  // 'applied'  -> props changed + rerender enqueued (watch edited_url)
  // 'noop'     -> understood, but nothing needed changing
  // 'error'    -> a human-readable failure (key missing, bad output, etc.)
  kind: 'applied' | 'noop' | 'error'
  message: string
  // The keys the model reported changing (for a friendly chat summary). Optional.
  changes?: string[]
  // The saved props, echoed back so the editor's live <Player> preview can update
  // optimistically (before the full re-render lands). Only on `applied`.
  props?: unknown
}> {
  const msg = (input.message || '').trim()
  if (!input.runId || !input.userId) return { ok: false, kind: 'error', message: 'Not signed in for this run.' }
  if (!msg) return { ok: false, kind: 'error', message: 'Type what you want to change first.' }

  const db = adminClient()
  // Load + ownership check (admin client bypasses RLS — verify the owner).
  const { data: run, error: readErr } = await db.database
    .from('runs')
    .select('id, user_id, props, props_edited')
    .eq('id', input.runId)
    .maybeSingle()
  if (readErr) return { ok: false, kind: 'error', message: 'Could not load this run.' }
  if (!run) return { ok: false, kind: 'error', message: 'Run not found.' }
  const r = run as { user_id?: string; props?: unknown; props_edited?: unknown }
  if (r.user_id !== input.userId) return { ok: false, kind: 'error', message: 'You do not own this run.' }

  const edited = (r.props_edited && typeof r.props_edited === 'object' ? r.props_edited : null) as ChatProps | null
  const clean = (r.props && typeof r.props === 'object' ? r.props : null) as ChatProps | null
  const current = edited && Array.isArray(edited.scenes) ? edited : clean
  if (!current || !Array.isArray(current.scenes) || current.scenes.length === 0) {
    return { ok: false, kind: 'error', message: 'This run has no editable props yet.' }
  }

  const apiKey = process.env.OPENROUTER_API_KEY
  if (!apiKey) {
    // Graceful degradation — the UI still works, just tells the user what to set.
    return {
      ok: false,
      kind: 'error',
      message:
        'Natural-language edits need an OpenRouter key. Set OPENROUTER_API_KEY in the environment, or use the Advanced panel to edit by hand.',
    }
  }

  const model = process.env.OPENROUTER_EDIT_MODEL || DEFAULT_EDIT_MODEL

  const system = [
    'You are the editing engine for a brand-video editor. You receive a video render-props JSON object and a natural-language change request.',
    'Return the COMPLETE updated props JSON (same schema, same scene order, same scene count). Change ONLY what the request implies; copy everything else through unchanged.',
    'Rules:',
    '- Never add, remove, or reorder scenes. Never change a scene id or archetype.',
    '- Scene copy lives in scene.data (title, subtitle, kicker, heading, headline, caption, statement, overlayTitle, bullets[], cards[], entities[], etc.). Edit those strings to honor wording requests.',
    '- Sizing/position lives in scene.data.geo.<key> (e.g. titleFontSize, subtitleFontSize, statementFontSize, plateW, plateH, cardW, shotH). "bigger"/"smaller" => adjust the relevant geo font size by ~15-30%. Create scene.data.geo if absent.',
    '- Timing: scene.in_frame / scene.out_frame are absolute frame numbers; total_frames is the whole video. "longer"/"shorter scene N" => widen/narrow that scene\'s [in_frame,out_frame] and SHIFT all later scenes + total_frames so nothing overlaps and there are no gaps. fps is fixed.',
    '- Color/mood: theme.accent / theme.bg / theme.text are hex. "more energetic"/"warmer"/"calmer" => nudge theme.accent (and tasteful copy punch) accordingly.',
    '- Output STRICT JSON only — no markdown, no prose, no code fences. The very first character must be "{".',
  ].join('\n')

  const user = [
    'CURRENT PROPS:',
    describeForLLM(current),
    '',
    'CHANGE REQUEST:',
    msg,
    '',
    'Return the full updated props JSON now.',
  ].join('\n')

  let raw: string
  try {
    const ctrl = new AbortController()
    const to = setTimeout(() => ctrl.abort(), 60_000)
    const resp = await fetch(OPENROUTER_URL, {
      method: 'POST',
      signal: ctrl.signal,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        response_format: { type: 'json_object' },
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
      }),
    }).finally(() => clearTimeout(to))
    if (!resp.ok) {
      const detail = await resp.text().catch(() => '')
      return { ok: false, kind: 'error', message: `The edit model is unavailable right now (HTTP ${resp.status}).${detail ? ' ' + detail.slice(0, 120) : ''}` }
    }
    const json = (await resp.json()) as { choices?: Array<{ message?: { content?: string } }> }
    raw = json?.choices?.[0]?.message?.content ?? ''
  } catch (e) {
    const m = (e as { name?: string })?.name === 'AbortError' ? 'The edit model took too long to respond.' : 'Could not reach the edit model.'
    return { ok: false, kind: 'error', message: m }
  }

  // Parse — tolerate accidental code fences / leading prose by slicing to the JSON.
  let parsed: unknown
  try {
    const start = raw.indexOf('{')
    const end = raw.lastIndexOf('}')
    const slice = start >= 0 && end > start ? raw.slice(start, end + 1) : raw
    parsed = JSON.parse(slice)
  } catch {
    return { ok: false, kind: 'error', message: 'The edit model returned something I could not apply. Try rephrasing.' }
  }

  const updated = sanitizeProps(current, parsed)
  if (!updated) {
    return { ok: false, kind: 'error', message: 'That edit would break the video structure, so I skipped it. Try a smaller change.' }
  }

  // Detect whether anything actually changed (cheap deep-equal via JSON).
  const unchanged = JSON.stringify(updated) === JSON.stringify(current)
  if (unchanged) {
    return { ok: true, kind: 'noop', message: 'Nothing needed changing for that — the video already matches.' }
  }

  // Persist + enqueue a re-render through the EXISTING backend.
  const saved = await saveEditedProps({ runId: input.runId, userId: input.userId, props: updated })
  if (!saved.ok) return { ok: false, kind: 'error', message: 'Could not save the edit: ' + (saved.error || 'unknown') }
  const queued = await requestReRender({ runId: input.runId, userId: input.userId })
  if (!queued.ok) return { ok: false, kind: 'error', message: 'Saved your edit, but could not start the re-render: ' + (queued.error || 'unknown') }

  // Summarize which top-level areas changed for a friendly chat line.
  const changes: string[] = []
  try {
    if (JSON.stringify(updated.scenes) !== JSON.stringify(current.scenes)) changes.push('scenes')
    if (JSON.stringify(updated.theme) !== JSON.stringify(current.theme)) changes.push('theme')
    if (updated.total_frames !== current.total_frames) changes.push('timing')
  } catch {
    /* best-effort */
  }

  return {
    ok: true,
    kind: 'applied',
    message: 'On it — applying that and re-rendering your video.',
    changes,
    props: updated,
  }
}

// ─────────────────────────────── Developer mode ───────────────────────────────
// Key-gated "see the machinery" access for hackathon judges. A signed-in account
// pairs a secret DEV_MODE_KEY (validated SERVER-SIDE only) and gets a row in the
// `developers` table — `developer = true` unlocks /inside/[runId] forever for that
// account. The key never leaves the server: it is compared to process.env.DEV_MODE_KEY
// and is NEVER returned, logged, or shipped to the browser.

/**
 * Validate a dev-mode key (server-only) and, on match, set the developer flag for the
 * given signed-in user. Idempotent: re-pairing the same account is a no-op success.
 * Returns only `{ ok }` — never the key or the env value.
 */
export async function pairDeveloper(input: { key: string; userId: string }): Promise<{ ok: boolean }> {
  const expected = process.env.DEV_MODE_KEY
  // Reject if the server has no key configured, or the supplied key doesn't match.
  // Constant-ish compare; we intentionally do not branch-log the comparison.
  if (!expected || !input.key || input.key !== expected) return { ok: false }
  if (!input.userId) return { ok: false }

  const db = adminClient()
  // Upsert-by-hand (read → insert-or-noop) so re-pairing is safe and we never throw on
  // a duplicate. The admin key bypasses RLS, so this writes for any signed-in account.
  const { data: existing } = await db.database
    .from('developers')
    .select('user_id')
    .eq('user_id', input.userId)
    .maybeSingle()

  if (!existing) {
    const { error } = await db.database
      .from('developers')
      .insert([{ user_id: input.userId, developer: true, source: 'dev_mode_key' }])
    if (error) throw new Error('developers.insert: ' + JSON.stringify(error))
  }
  return { ok: true }
}

/** Read back the developer flag for a user. Used to gate /inside/[runId]. */
export async function isDeveloper(userId: string | null | undefined): Promise<boolean> {
  if (!userId) return false
  const db = adminClient()
  const { data } = await db.database
    .from('developers')
    .select('developer')
    .eq('user_id', userId)
    .maybeSingle()
  return !!(data && (data as { developer?: boolean }).developer)
}

/**
 * Admin-client fetch of a run + its run_events, so a developer can view ANY run
 * (including the canonical featured run they don't own). Returns null if not found.
 * Bypasses RLS by design — only reachable behind the isDeveloper() gate in /inside.
 */
export async function readInsideRun(runId: string): Promise<{
  run: Record<string, unknown>
  events: Record<string, unknown>[]
} | null> {
  if (!runId) return null
  const db = adminClient()
  const { data: run } = await db.database
    .from('runs')
    .select()
    .eq('id', runId)
    .maybeSingle()
  if (!run) return null

  const { data: events } = await db.database
    .from('run_events')
    .select()
    .eq('run_id', runId)
    .order('seq', { ascending: true })

  return {
    run: run as Record<string, unknown>,
    events: (events as Record<string, unknown>[]) ?? [],
  }
}
