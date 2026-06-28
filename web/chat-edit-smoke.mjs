// Faithful, READ-ONLY verification of the chat-editor NL-edit loop against the LIVE
// backend. It does NOT mutate the real run and does NOT enqueue a re-render: it loads
// the run's real props, runs the EXACT OpenRouter prompt editViaChat() uses, applies a
// VERBATIM copy of sanitizeProps(), and then inspects the resulting TIMELINE for the
// flagged risk (overlaps/gaps after a timing edit). $0: uses the :free Hermes variant.
import { readFileSync } from 'node:fs'
import { createClient, createAdminClient } from '@insforge/sdk'

const env = {}
for (const line of readFileSync(new URL('./.env.local', import.meta.url), 'utf8').split('\n')) {
  const m = line.match(/^([A-Z0-9_]+)=(.*)$/); if (m) env[m[1]] = m[2].trim()
}
// Fall back to process.env for keys not in .env.local (e.g. OPENROUTER_API_KEY lives in ~/.hermes/.env)
for (const k of ['OPENROUTER_API_KEY', 'OPENROUTER_EDIT_MODEL']) if (!env[k] && process.env[k]) env[k] = process.env[k]
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const RUN_ID = process.argv[2] || 'e412358b-f138-4db3-9c21-08458f8d2d52'
const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
// $0: try free models in order until one answers (production uses the PAID Hermes slug).
const MODELS = process.env.OPENROUTER_EDIT_MODEL ? [process.env.OPENROUTER_EDIT_MODEL] : [
  'nousresearch/hermes-3-llama-3.1-405b:free',
  'meta-llama/llama-3.3-70b-instruct:free',
  'deepseek/deepseek-chat-v3-0324:free',
  'qwen/qwen-2.5-72b-instruct:free',
]

// ── VERBATIM copy of sanitizeProps from app/actions.ts (keep in sync) ──
const EDITABLE_TOP_KEYS = new Set(['scenes', 'theme', 'total_frames', 'music_path', 'music_level', 'voiceover'])
function sanitizeProps(original, candidate) {
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return null
  const c = candidate
  if (!Array.isArray(c.scenes) || c.scenes.length === 0) return null
  const origScenes = Array.isArray(original.scenes) ? original.scenes : []
  if (c.scenes.length !== origScenes.length) return null
  const scenes = c.scenes.map((s, i) => {
    const orig = origScenes[i] || {}
    if (!s || typeof s !== 'object') return orig
    const sc = s
    const inF = Number(sc.in_frame ?? orig.in_frame ?? 0)
    const outF = Number(sc.out_frame ?? orig.out_frame ?? 0)
    return {
      ...orig, ...sc,
      id: orig.id ?? sc.id,
      archetype: orig.archetype ?? sc.archetype,
      in_frame: Number.isFinite(inF) ? inF : orig.in_frame ?? 0,
      out_frame: Number.isFinite(outF) ? outF : orig.out_frame ?? 0,
      cues: orig.cues ?? sc.cues ?? [],
    }
  })
  const out = { ...original, scenes }
  for (const k of EDITABLE_TOP_KEYS) { if (k === 'scenes') continue; if (k in c && c[k] != null) out[k] = c[k] }
  return out
}
// ── system prompt VERBATIM from editViaChat ──
const SYSTEM = [
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

let usedModel = '(none)'
async function callModel(current, msg) {
  const user = ['CURRENT PROPS:', JSON.stringify(current, null, 0), '', 'CHANGE REQUEST:', msg, '', 'Return the full updated props JSON now.'].join('\n')
  let lastErr = ''
  for (const model of MODELS) {
    for (let attempt = 1; attempt <= 2; attempt++) {
      const ctrl = new AbortController(); const to = setTimeout(() => ctrl.abort(), 60_000)
      const resp = await fetch(OPENROUTER_URL, {
        method: 'POST', signal: ctrl.signal,
        headers: { Authorization: `Bearer ${env.OPENROUTER_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, temperature: 0.2, response_format: { type: 'json_object' }, messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: user }] }),
      }).finally(() => clearTimeout(to))
      if (resp.ok) { const j = await resp.json(); usedModel = model; return j?.choices?.[0]?.message?.content ?? '' }
      const d = await resp.text().catch(() => ''); lastErr = `HTTP ${resp.status} ${d.slice(0, 120)}`
      if (resp.status === 429 || resp.status >= 500) { if (attempt < 2) { await new Promise(r => setTimeout(r, 6000)); continue } else { log(`    (${model} unavailable: ${resp.status} — next model)`); break } }
      throw new Error(lastErr)
    }
  }
  throw new Error(`all models unavailable; last: ${lastErr}`)
}
function parseJson(raw) {
  const s = raw.indexOf('{'), e = raw.lastIndexOf('}')
  return JSON.parse(s >= 0 && e > s ? raw.slice(s, e + 1) : raw)
}
// Timeline integrity check: scenes sorted by in_frame must be contiguous & non-overlapping
function checkTimeline(props) {
  const sc = (props.scenes || []).map((s, i) => ({ i, in: Number(s.in_frame), out: Number(s.out_frame) }))
  const issues = []
  for (const s of sc) { if (!Number.isFinite(s.in) || !Number.isFinite(s.out) || s.out <= s.in) issues.push(`scene ${s.i} bad bounds [${s.in},${s.out}]`) }
  const sorted = [...sc].sort((a, b) => a.in - b.in)
  for (let k = 1; k < sorted.length; k++) {
    const prev = sorted[k - 1], cur = sorted[k]
    if (cur.in < prev.out) issues.push(`OVERLAP: scene ${prev.i} out=${prev.out} > scene ${cur.i} in=${cur.in}`)
    else if (cur.in > prev.out) issues.push(`GAP: scene ${prev.i} out=${prev.out} .. scene ${cur.i} in=${cur.in} (${cur.in - prev.out}f hole)`)
  }
  const last = sorted[sorted.length - 1]
  const tf = Number(props.total_frames)
  if (Number.isFinite(tf) && last && tf < last.out) issues.push(`total_frames ${tf} < last scene out ${last.out}`)
  return issues
}

const anon = createClient({ baseUrl: env.NEXT_PUBLIC_INSFORGE_URL, anonKey: env.NEXT_PUBLIC_INSFORGE_ANON_KEY })
const db = createAdminClient({ baseUrl: env.INSFORGE_URL, apiKey: env.INSFORGE_API_KEY })

const q = await db.database.from('runs').select('id, props, props_edited').eq('id', RUN_ID).maybeSingle?.() ??
          await db.database.from('runs').select('id, props, props_edited').eq('id', RUN_ID)
const row = q.data?.id ? q.data : q.data?.[0]
if (!row) { log('FAIL: run not found', RUN_ID); process.exit(1) }
const current = (row.props_edited && Array.isArray(row.props_edited.scenes)) ? row.props_edited : row.props
if (!current?.scenes?.length) { log('FAIL: run has no editable props'); process.exit(1) }
log(`loaded run ${RUN_ID}: ${current.scenes.length} scenes, total_frames=${current.total_frames}, accent=${current.theme?.accent}`)
log('baseline timeline issues:', JSON.stringify(checkTimeline(current)))

const TESTS = [
  { name: 'color', msg: 'Make the accent color teal.', kind: 'safe' },
  { name: 'sizing', msg: 'Make the title bigger.', kind: 'safe' },
  { name: 'timing', msg: 'Make the second scene about 1.5 seconds longer.', kind: 'risk' },
]
let pass = 0, fail = 0
for (const t of TESTS) {
  try {
    log(`\n── EDIT [${t.name}] "${t.msg}"`)
    const raw = await callModel(current, t.msg)
    let parsed; try { parsed = parseJson(raw) } catch { log(`  ${t.name}: model returned unparseable JSON (len ${raw.length})`); fail++; continue }
    const updated = sanitizeProps(current, parsed)
    if (!updated) { log(`  ${t.name}: sanitizeProps REJECTED (structure broke)`); fail++; continue }
    const changedAccent = updated.theme?.accent !== current.theme?.accent
    const changedTiming = updated.total_frames !== current.total_frames || JSON.stringify(updated.scenes.map(s => [s.in_frame, s.out_frame])) !== JSON.stringify(current.scenes.map(s => [s.in_frame, s.out_frame]))
    const changedScenes = JSON.stringify(updated.scenes) !== JSON.stringify(current.scenes)
    const issues = checkTimeline(updated)
    log(`  changed: accent=${changedAccent} timing=${changedTiming} scenes=${changedScenes}`)
    if (t.name === 'color') log(`  accent ${current.theme?.accent} -> ${updated.theme?.accent}`)
    if (t.name === 'timing') log(`  total_frames ${current.total_frames} -> ${updated.total_frames}; bounds: ${JSON.stringify(updated.scenes.map(s => [s.in_frame, s.out_frame]))}`)
    log(`  TIMELINE ISSUES: ${issues.length ? JSON.stringify(issues) : 'none'}`)
    const ok = changedScenes && issues.length === 0
    log(`  [${t.name}] ${ok ? 'PASS' : 'CONCERN'}${t.kind === 'risk' && issues.length ? ' <-- flagged timing risk reproduced' : ''}`)
    ok ? pass++ : fail++
  } catch (e) { log(`  ${t.name}: ERROR ${String(e).slice(0, 200)}`); fail++ }
}
log(`\nCHAT-EDIT-SMOKE done: ${pass} clean / ${fail} concern (read-only; nothing saved, no re-render). model=${usedModel}`)
