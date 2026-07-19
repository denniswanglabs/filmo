'use client'
// Walkrec beta workspace — the Ploy-shaped page: ONE white canvas in browser
// chrome where everything happens (page reads, the live recording, the beats,
// the film), and ONE timeline rail on the left merging conversation + work
// updates chronologically. Direct React port of the validated local viewer;
// same event contract, agent_events + storage instead of localhost.
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { getAgentRun, listMyRuns, sendDirectorMessage, type AgentEvent } from '../../actions'

const VERBS: Record<string, string> = {
  read: 'Scouting', decide: 'Framing', film: 'Rolling',
  design: 'Cutting', assemble: 'Printing', review: 'Grading',
}
function md(text: string) {
  // Ploy-grammar light markdown: **bold leads**, keep everything else plain.
  const esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  return esc.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
}

const THREAD_KINDS = new Set([
  'run.start', 'read.page', 'read.quotes', 'decide.plan', 'decide.guard',
  'film.recording', 'film.shot', 'film.failed', 'design.beat', 'review.lint',
  'review.finding', 'review.pass', 'review.apply', 'review.done',
  'assemble.film', 'run.error', 'chat.user', 'chat.director', 'say.step',
])

// VOICE: the agent SPEAKS in prose (always visible, full sentences) and
// leaves work RECEIPTS (collapsed, verb + result). A thread of nothing but
// receipts reads as a log; a thread of nothing but prose hides the work.
const PROSE_KINDS = new Set(['chat.director', 'say.step'])

function whenShort(ts: number): string {
  const d = new Date(ts * 1000)
  const days = Math.round((Date.now() - ts * 1000) / 86400000)
  if (days < 1) return 'Updated today'
  if (days === 1) return 'Updated yesterday'
  return 'Updated ' + d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

type LocalMsg = { ts: number; kind: 'user' | 'dir'; text: string }

function reduce(evts: AgentEvent[]) {
  const S = {
    pages: [] as AgentEvent[], plan: [] as string[], beats: [] as AgentEvent[],
    review: [] as AgentEvent[], film: '', filmSeq: 0, phase: 'read',
    roundResetAt: 0,
    status: '', lastTitle: '', site: '', done: false, logo: '',
  }
  for (const e of evts) {
    const k = e.kind
    if (k === 'run.start') {
      // Titles: "Opening https://x" (hosted) or "... for https://x" (local).
      const m = e.title.match(/(https?:\/\/\S+)/)
      if (m) S.site = m[1]
      S.done = false
    }
    if (!S.site && k === 'read.page') {
      const m = e.title.match(/(https?:\/\/\S+)/)
      if (m) S.site = m[1]
    }
    if (k === 'read.page') { S.pages.push(e); S.phase = 'read' }
    if (k === 'brand.logo' && e.artifact_url) S.logo = e.artifact_url
    if (k === 'decide.plan') { S.plan = e.detail.split('\n'); S.phase = 'decide' }
    if (k.startsWith('film.')) S.phase = 'film'
    if (k === 'assemble.render') { S.roundResetAt = e.seq }
    if (k === 'design.beat' && e.artifact_url) {
      // A new render round replaces the WHOLE beat set — without this, a
      // dropped beat's stale segment survives at the strip's tail.
      if (S.roundResetAt && e.seq > S.roundResetAt
          && S.beats.some((b) => b.seq <= S.roundResetAt)) {
        S.beats = S.beats.filter((b) => b.seq > S.roundResetAt)
      }
      // A review round re-emits its beats — REPLACE by beat index (the
      // title carries "Beat N:") so the timeline strip never shows a
      // mixed set of superseded and current beats.
      const m = e.title.match(/^Beat (\d+):/)
      const idx = m ? parseInt(m[1], 10) : S.beats.length + 1
      const at = S.beats.findIndex((b) => (b.title.match(/^Beat (\d+):/) || [])[1] === String(idx))
      if (at >= 0) S.beats[at] = e
      else S.beats.push(e)
      S.phase = 'design'
    }
    if (k === 'assemble.render') S.phase = 'assemble'
    if (k.startsWith('review.')) S.phase = 'review'
    if (k === 'assemble.film') { S.film = e.artifact_url; S.filmSeq = e.seq }
    if (k === 'review.pass' || k === 'review.done') S.review.push(e)
    if (k === 'run.done') { S.phase = 'done'; S.status = 'finished'; S.done = true }
    if (k === 'run.error') { S.phase = 'done'; S.status = 'failed'; S.done = true }
    S.lastTitle = e.title
  }
  return S
}

export default function Workspace({ runKey, getToken }: {
  runKey: string; getToken: () => Promise<string | null>
}) {
  const [evts, setEvts] = useState<AgentEvent[]>([])
  const [liveUrl, setLiveUrl] = useState('')
  const [liveFresh, setLiveFresh] = useState(false)
  const [liveTick, setLiveTick] = useState(0)
  const [queueAhead, setQueueAhead] = useState<number | null>(null)
  const [filmUrl, setFilmUrl] = useState('')
  const [localMsgs, setLocalMsgs] = useState<LocalMsg[]>([])
  const [input, setInput] = useState('')
  const [pinned, setPinned] = useState<AgentEvent | null>(null)
  const [tab, setTab] = useState<'film' | 'films'>('film')
  // The films this account has already produced — the library behind the
  // Films tab. Loaded once, lazily, when the tab is first opened.
  const [library, setLibrary] = useState<{
    id: string; brand: string; url: string; ts: number; status: string
  }[] | null>(null)
  const [openWork, setOpenWork] = useState<Record<number, boolean>>({})
  const [pending, setPending] = useState(false)
  const phaseStart = useRef(Date.now())
  const lastPhase = useRef('')
  const threadRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playT, setPlayT] = useState(0)
  const evtsRef = useRef<AgentEvent[]>([])
  // FULL-SCREEN SURFACE CONTRACT: the page template wraps content in a
  // framer-motion fade with a transform — a transformed ancestor hijacks
  // position:fixed and inherits its opacity. The workspace therefore
  // PORTALS to document.body, outside any page-transition wrapper.
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])

  const S = reduce(evts)

  // Event poll (1.5s) — the same contract as the local viewer.
  useEffect(() => {
    let stop = false
    const tick = async () => {
      if (stop) return
      try {
        const after = evtsRef.current.length
          ? evtsRef.current[evtsRef.current.length - 1].seq : -1
        // Rows whose artifact hasn't attached yet (insert-first sink):
        // ask the server to re-read them until the PATCH lands.
        const pendingArtifacts = evtsRef.current
          .filter((e) => !e.artifact_url && (
            e.kind === 'design.beat' || e.kind === 'assemble.film'
            || e.kind === 'read.page' || e.kind === 'brand.logo'
            || e.kind === 'film.shot' || e.kind === 'review.done'))
          .map((e) => e.seq)
        const res = await getAgentRun(runKey, after, (await getToken()) || '',
          pendingArtifacts)
        if (!('error' in res)) {
          let next = evtsRef.current
          if (res.refreshed && res.refreshed.length) {
            const bySeq = new Map(res.refreshed.map((e) => [e.seq, e]))
            next = next.map((e) => bySeq.get(e.seq) || e)
          }
          if (res.events.length) next = [...next, ...res.events]
          if (next !== evtsRef.current) {
            evtsRef.current = next
            setEvts(next)
          }
          if (typeof res.queueAhead === 'number') setQueueAhead(res.queueAhead)
          else if (res.events.length) setQueueAhead(null)
          if (res.filmUrl) setFilmUrl(res.filmUrl)
        }
      } catch { /* transient */ }
      setTimeout(tick, 1500)
    }
    tick()
    return () => { stop = true }
  }, [runKey, getToken])

  useEffect(() => {
    if (tab !== 'films' || library !== null) return
    let stop = false
    ;(async () => {
      try {
        const res = await listMyRuns((await getToken()) || '')
        if (stop || 'authError' in res) return
        setLibrary(res.runs
          .filter((r) => r.final_url)
          .map((r) => ({
            id: r.id,
            brand: r.brand || r.company_url || 'Launch film',
            url: r.final_url as string,
            ts: Date.parse(r.created_at) / 1000,
            status: r.status,
          })))
      } catch { /* transient */ }
    })()
    return () => { stop = true }
  }, [tab, library, getToken])

  // Live viewport probe (~1s): the frame URL 404s via the proxy when stale.
  useEffect(() => {
    let stop = false
    const probe = async () => {
      if (stop) return
      try {
        const res = await getAgentRun(runKey, 1e9, (await getToken()) || '')
        if (!('error' in res)) setLiveUrl(res.liveUrl)
      } catch { /* once */ }
    }
    probe()
    const iv = setInterval(() => setLiveTick((t) => t + 1), 1200)
    return () => { stop = true; clearInterval(iv) }
  }, [runKey, getToken])

  useEffect(() => {
    if (S.phase !== lastPhase.current) {
      lastPhase.current = S.phase
      phaseStart.current = Date.now()
    }
  })
  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [evts.length, localMsgs.length])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text) return
    setInput('')
    setLocalMsgs((m) => [...m, { ts: Date.now() / 1000, kind: 'user', text }])
    setPending(true)
    const res = await sendDirectorMessage(runKey, text, (await getToken()) || '')
    if ('error' in res) {
      // An out-of-credits refusal explains itself; anything else is a blip.
      const msg = ('message' in res && res.message)
        ? res.message
        : 'That did not go through — try again.'
      setPending(false)
      setLocalMsgs((m) => [...m, { ts: Date.now() / 1000, kind: 'dir', text: msg }])
    }
  }, [input, runKey, getToken])

  // Merge thread items chronologically; server chat events replace local echoes.
  const items: Array<
    | { ts: number; type: 'user' | 'dir'; text: string }
    | { ts: number; type: 'work'; e: AgentEvent }
  > = []
  let sawDirectorReply = false
  for (const e of evts) {
    if (!THREAD_KINDS.has(e.kind)) continue
    if (e.kind === 'chat.user') items.push({ ts: e.ts, type: 'user', text: e.title })
    else if (PROSE_KINDS.has(e.kind)) {
      items.push({ ts: e.ts, type: 'dir', text: e.title })
      if (e.kind === 'chat.director') sawDirectorReply = true
    } else items.push({ ts: e.ts, type: 'work', e })
  }
  useEffect(() => {
    if (pending && sawDirectorReply) setPending(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evts.length])
  for (const m of localMsgs) {
    const dupe = evts.some((e) =>
      (e.kind === 'chat.user' || e.kind === 'chat.director')
      && e.title === m.text && Math.abs(e.ts - m.ts) < 60)
    if (!dupe) items.push({ ts: m.ts, type: m.kind, text: m.text })
  }
  items.sort((a, b) => a.ts - b.ts)

  const working = !S.done
  const host = (S.site || '').replace(/^https?:\/\//, '').split('/')[0]
  const brandTitle = host
    ? host.split('.')[0].charAt(0).toUpperCase()
      + host.split('.')[0].slice(1) + ' launch film'
    : 'Launch film'
  const verb = VERBS[S.phase] || 'Working'
  const elapsed = Math.round((Date.now() - phaseStart.current) / 1000)

  // The ONE screen's content.
  let screen: React.ReactNode = null
  let pill = ''
  const lastPage = S.pages[S.pages.length - 1]
  if (tab === 'films') {
    screen = library === null ? (
      <div className="wk-text"><div className="big">Loading your films…</div></div>
    ) : library.length === 0 ? (
      <div className="wk-text">
        <div className="big">No finished films yet</div>
        <div className="small">Every film you produce lands here.</div>
      </div>
    ) : (
      <div className="wk-library">
        {library.map((f) => (
          <a key={f.id} className="wk-filmcard" href={`/runs/${f.id}`}>
            <div className="prev">
              <video src={`${f.url}#t=2`} preload="metadata" muted playsInline />
            </div>
            <div className="meta">
              <div className="name">{f.brand}</div>
              <div className="sub">{whenShort(f.ts)}</div>
              <div className="open">Open film</div>
            </div>
          </a>
        ))}
      </div>
    )
    pill = library ? `${library.length} film${library.length === 1 ? '' : 's'} produced` : 'films'
  } else if (pinned) {
    screen = <img src={pinned.artifact_url} alt="" />
    pill = pinned.title
  } else if (liveFresh && working) {
    screen = <img src={`${liveUrl}&t=${liveTick}`} alt="" />
    pill = `Recording ${S.site || ''}`
  } else if (evts.length === 0 && working) {
    // Queue truth (F8): nothing has happened yet — say where the build is.
    screen = (
      <div className="wk-text">
        <div className="big">
          {queueAhead === null ? 'Warming up…'
            : queueAhead === 0 ? 'Up next'
              : `In line at the studio`}
        </div>
        <div className="small">
          {queueAhead === null
            ? 'Connecting to the studio.'
            : queueAhead === 0
              ? 'The studio is opening your site now.'
              : `${queueAhead} build${queueAhead === 1 ? '' : 's'} ahead of you — the studio films one at a time.`}
        </div>
      </div>
    )
    pill = queueAhead && queueAhead > 0 ? `queued · ${queueAhead} ahead` : 'starting'
  } else if (S.phase === 'read') {
    screen = lastPage?.artifact_url ? <img src={lastPage.artifact_url} alt="" /> : null
    pill = lastPage ? lastPage.title.replace('Read ', '') : (S.site || 'opening…')
  } else if (S.phase === 'decide') {
    screen = (
      <div className="wk-text">
        <div className="big">{S.plan.map((p, i) => <div key={i}>{p}</div>)}</div>
        <div className="small">The moments a customer cares about — the site's own words.</div>
      </div>
    )
    pill = S.site
  } else if (S.phase === 'film') {
    screen = <div className="wk-text"><div className="big">{S.lastTitle}</div></div>
    pill = S.site
  } else if (['design', 'assemble', 'review'].includes(S.phase)) {
    screen = S.beats.length ? (
      <div className="wk-grid">
        {S.beats.map((b) => (
          <div key={b.seq} className="beat"><img src={b.artifact_url} alt="" /></div>
        ))}
      </div>
    ) : (
      <div className="wk-text">
        <div className="big">Printing the film</div>
        <div className="small">The beat board fills in as scenes land.</div>
      </div>
    )
    pill = S.phase === 'review' ? 'Grading — story and coherence' : 'Cutting — beat by beat'
  } else {
    if (!S.film && filmUrl) S.film = filmUrl
    if (S.film) {
      const starts = S.beats.map((b) => {
        const m = b.detail.match(/· ([\d.]+)s/)
        return m ? parseFloat(m[1]) : NaN
      })
      const seekable = starts.some((s) => !isNaN(s))
      let active = -1
      if (seekable) {
        for (let i = 0; i < starts.length; i++) {
          if (!isNaN(starts[i]) && playT >= starts[i]) active = i
        }
      }
      screen = (
        <div className="wk-playerwrap">
          <video ref={videoRef} src={S.film} controls muted
            onTimeUpdate={(ev) => setPlayT((ev.target as HTMLVideoElement).currentTime)} />
          {S.beats.length ? (
            <div className="wk-timeline">
              {S.beats.map((b, i) => (
                <div key={b.seq}
                  className={'seg' + (i === active ? ' on' : '')}
                  title={b.detail}
                  onClick={() => {
                    const v = videoRef.current
                    if (v && !isNaN(starts[i])) { v.currentTime = starts[i]; v.play() }
                  }}>
                  <img src={b.artifact_url} alt="" />
                  <span>{b.title.replace(/^Beat \d+:\s*/, '').split(' (')[0]}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )
    } else {
      screen = <div className="wk-text"><div className="big">{S.status === 'failed' ? 'The run failed.' : 'Finished.'}</div></div>
    }
    pill = S.film ? `film · ${S.review.length ? 'review passed' : 'final'}` : ''
  }

  // Live-frame freshness: try turning it on whenever working (img onError flips off).
  useEffect(() => {
    // The probe below owns liveFresh; the tick only advances the counter.
  }, [liveTick, working, liveUrl])

  if (!mounted) return null
  return createPortal(
    <div className="wk-root">
      <div className="wk-iconrail">
        <div className="wk-brand" title={S.site || 'brand'}>
          {S.logo
            ? <img src={S.logo} alt="" />
            : <span>{(host || 'F')[0].toUpperCase()}</span>}
        </div>
        <a className="wk-ic" href="/" title="All builds">
          <svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round"/></svg>
          <i>Builds</i>
        </a>
        <button className={'wk-ic' + (tab === 'film' ? ' on' : '')} onClick={() => setTab('film')} title="This film">
          <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2.5" stroke="currentColor" strokeWidth="2" fill="none"/><path d="M10 9.5v5l4.5-2.5z" fill="currentColor"/></svg>
          <i>Film</i>
        </button>
        <button className={'wk-ic' + (tab === 'films' ? ' on' : '')} onClick={() => setTab('films')} title="Films you've made">
          <svg viewBox="0 0 24 24"><rect x="3" y="4" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/><rect x="13" y="4" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/><rect x="3" y="13" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/><rect x="13" y="13" width="8" height="7" rx="1.5" stroke="currentColor" strokeWidth="2" fill="none"/></svg>
          <i>Films</i>
        </button>
        <div className="wk-railspace" />
        <div className="wk-filmomark" title="Filmo">
          <svg viewBox="14 13 56 56"><path fillRule="evenodd" fill="#3B82F6" d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"/></svg>
        </div>
      </div>
      <div className="wk-rail">
        <div className="wk-railhead">
          <div className="wk-blob" />
          <div>
            <h1>{brandTitle} <span className="wk-betachip">beta</span></h1>
            <div className="sub">{S.done ? (S.status || 'finished') : 'live'}</div>
          </div>
        </div>
        <div className="wk-thread" ref={threadRef}>
          {items.map((it, i) => {
            if (it.type !== 'work') {
              return it.type === 'user'
                ? <div key={i} className={'t-user' + (pending && i === items.length - 1 ? ' dim' : '')}>{it.text}</div>
                : <div key={i} className="t-dir"
                    dangerouslySetInnerHTML={{ __html: md(it.text) }} />
            }
            const e = it.e
            const thumb = e.artifact_url && !e.artifact_url.includes('.mp4')
            const open = !!openWork[e.seq]
            return (
              <div key={i} className="t-work">
                <button className="t-chev" onClick={() =>
                  setOpenWork((o) => ({ ...o, [e.seq]: !o[e.seq] }))}>
                  <svg viewBox="0 0 16 16" style={{ transform: open ? 'rotate(90deg)' : 'none' }}>
                    <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
                  </svg>
                </button>
                <div className="t-workbody">
                  <div className="t-workline" onClick={() =>
                    setOpenWork((o) => ({ ...o, [e.seq]: !o[e.seq] }))}>
                    <b>{e.title}</b>
                  </div>
                  {open ? (
                    <div className="t-workdetail">
                      {e.detail ? <div>{e.detail}</div> : null}
                      {thumb ? (
                        <img src={e.artifact_url} alt=""
                          onClick={() => { setPinned(e); setTimeout(() => setPinned(null), 8000) }} />
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            )
          })}
          {working || pending ? (
            <div className="t-verb">
              <span className="wk-tailblob" />
              {pending ? 'Thinking…' : `${verb}… ${elapsed}s`}
            </div>
          ) : null}
        </div>
        <div className="wk-inputrow">
          <div className="wk-inputbox">
            <input value={input} placeholder="Tell the director what to change…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') send() }} />
            <button onClick={send} aria-label="Send">↑</button>
          </div>
        </div>
      </div>
      <div className="wk-canvaswrap">
        <div className="wk-canvas">
          <div className="wk-chrome">
            <div className="dots"><i /><i /><i /></div>
            <div className="wk-tabs">
              <button className={tab === 'film' ? 'on' : ''} onClick={() => setTab('film')}>Film</button>
              <button className={tab === 'films' ? 'on' : ''} onClick={() => setTab('films')}>Films</button>
            </div>
            <div className="wk-urlpill" title={S.site}>{host || '…'}</div>
            {pill ? <div className="wk-statuschip">{pill}</div> : null}
            {liveFresh && working ? <div className="rec" /> : null}
            {working ? (
              <img className="wk-liveprobe" src={`${liveUrl}&t=${liveTick}`}
                onLoad={() => setLiveFresh(true)}
                onError={() => setLiveFresh(false)} alt="" />
            ) : null}
          </div>
          <div className="wk-screen">{screen}</div>
        </div>
      </div>
      <style>{`
        .wk-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        .wk-iconrail { flex:0 0 72px; display:flex; flex-direction:column;
          align-items:center; gap:18px; padding:16px 0; border-right:1px solid #E6E6E3; }
        .wk-brand { width:40px; height:40px; border-radius:12px; overflow:hidden;
          background:#1B1B1A; color:#fff; display:flex; align-items:center;
          justify-content:center; font-weight:700; font-size:17px;
          box-shadow:0 2px 8px rgba(0,0,0,0.12); }
        .wk-brand img { width:100%; height:100%; object-fit:cover; }
        .wk-ic { display:flex; flex-direction:column; align-items:center; gap:4px;
          color:#8A8A86; background:none; border:none; cursor:pointer;
          text-decoration:none; font:inherit; }
        .wk-ic svg { width:22px; height:22px; }
        .wk-ic i { font-style:normal; font-size:10px; }
        .wk-ic.on, .wk-ic:hover { color:#1B1B1A; }
        .wk-railspace { flex:1; }
        .wk-filmomark svg { width:26px; height:26px; opacity:0.9; }
        .wk-tailblob { display:inline-block; width:16px; height:16px;
          background:radial-gradient(circle at 32% 30%, #7FB0FF, #3B82F6 58%, #1D4ED8);
          animation:wkmorph 2.4s ease-in-out infinite; position:relative; }
        .wk-tabs { display:flex; gap:2px; background:#F1F1EF; border-radius:8px;
          padding:2px; }
        .wk-tabs button { border:none; background:none; font:12px Inter,sans-serif;
          padding:4px 12px; border-radius:6px; color:#8A8A86; cursor:pointer; }
        .wk-tabs button.on { background:#fff; color:#1B1B1A;
          box-shadow:0 1px 2px rgba(0,0,0,0.06); }
        .t-user.dim { opacity:0.45; }
        .t-chev { border:none; background:none; padding:2px; cursor:pointer;
          color:#B6B6B2; flex-shrink:0; }
        .t-chev svg { width:14px; height:14px; transition:transform 0.15s; }
        .t-workbody { min-width:0; }
        .t-workline { cursor:pointer; }
        .t-workdetail { margin-top:6px; color:#8A8A86; }
        .t-workdetail img { width:150px; border-radius:8px; margin-top:6px;
          border:1px solid #E6E6E3; cursor:pointer; display:block; }
        .wk-rail { flex:0 0 380px; display:flex; flex-direction:column;
          border-right:1px solid #E6E6E3; }
        .wk-railhead { flex:0 0 62px; display:flex; align-items:center; gap:12px;
          padding:0 20px; }
        .wk-railhead h1 { font-size:14.5px; font-weight:700; margin:0; }
        .wk-railhead .sub { color:#8A8A86; font-size:12px; }
        /* STILL BY DEFAULT: the head mark is identity, not activity. The
           tail blob (wk-tailblob) is the thing that moves while working. */
        .wk-blob { width:36px; height:36px; position:relative; flex-shrink:0;
          background:radial-gradient(circle at 32% 30%, #7FB0FF, #3B82F6 58%, #1D4ED8);
          border-radius:44% 56% 52% 48% / 50% 46% 54% 50%; }
        .wk-blob::after { content:""; position:absolute; width:34%; height:34%;
          transform:translate(-46%, 8%);
          right:16%; top:26%; background:#fff; border-radius:50%;
        }
        @keyframes wkmorph {
          0%,100% { border-radius:58% 42% 55% 45% / 48% 60% 40% 52%; transform:scale(1); }
          33% { border-radius:42% 58% 38% 62% / 60% 42% 58% 40%; transform:scale(0.92); }
          66% { border-radius:52% 48% 62% 38% / 40% 55% 45% 60%; transform:scale(1.05); } }
        @keyframes wkspin { to { transform:rotate(360deg); } }
        @keyframes wkhole {
          0% { border-radius:52% 48% 50% 50% / 48% 52% 48% 52%;
               transform:translate(0,0) scale(1); }
          33% { border-radius:46% 54% 58% 42% / 54% 46% 52% 48%;
                transform:translate(-34%,30%) scale(0.9); }
          66% { border-radius:55% 45% 47% 53% / 45% 55% 50% 50%;
                transform:translate(-58%,-8%) scale(1.08); }
          100% { border-radius:52% 48% 50% 50% / 48% 52% 48% 52%;
                 transform:translate(0,0) scale(1); } }
        .wk-thread { flex:1; min-height:0; overflow-y:auto; padding:6px 20px 12px;
          display:flex; flex-direction:column; gap:12px; }
        .t-user { background:#fff; border:1px solid #E6E6E3; border-radius:12px;
          padding:10px 14px; font-size:13.5px; box-shadow:0 1px 2px rgba(0,0,0,0.03); }
        .t-dir { font-size:13.5px; line-height:1.55; }
        .t-work { color:#8A8A86; font-size:12.5px; display:flex; gap:8px;
          align-items:flex-start; }
        .t-work b { color:#6E6E6A; font-weight:600; }
        .t-work img { width:52px; border-radius:6px; border:1px solid #E6E6E3;
          cursor:pointer; flex-shrink:0; }
        .t-verb { color:#8A8A86; font-size:12.5px; display:flex; align-items:center;
          gap:8px; }
        .dotp { width:7px; height:7px; border-radius:4px; background:#3B82F6;
          animation:wkpulse 1.2s infinite; }
        @keyframes wkpulse { 0%,100%{opacity:1} 50%{opacity:0.25} }
        .wk-inputrow { flex:0 0 auto; padding:14px 20px 18px; }
        .wk-inputbox { display:flex; gap:8px; background:#fff;
          border:1px solid #E6E6E3; border-radius:14px; padding:10px 12px;
          box-shadow:0 1px 3px rgba(0,0,0,0.04); }
        .wk-inputbox input { flex:1; border:none; outline:none;
          font:13.5px Inter,sans-serif; background:transparent; }
        .wk-inputbox button { border:none; background:#1B1B1A; color:#fff;
          width:34px; height:34px; border-radius:17px; cursor:pointer;
          font-size:15px; }
        .wk-canvaswrap { flex:1 1 0; min-width:0; min-height:0; display:flex;
          align-items:stretch; justify-content:center; padding:18px; }
        .wk-canvas { flex:1; min-width:0; min-height:0; max-width:1240px;
          background:#fff; border-radius:16px; display:flex; flex-direction:column;
          overflow:hidden; box-shadow:0 1px 2px rgba(0,0,0,0.04),
          0 24px 70px -30px rgba(0,0,0,0.18); }
        .wk-chrome { flex:0 0 44px; display:flex; align-items:center; gap:14px;
          padding:0 16px; border-bottom:1px solid #E6E6E3; }
        .wk-chrome .dots { display:flex; gap:6px; }
        .wk-chrome .dots i { width:10px; height:10px; border-radius:5px;
          background:#E4E4E1; }
        .wk-urlpill { flex:1; max-width:520px; margin:0 auto;
          background:#F5F5F3; border-radius:8px; padding:5px 14px;
          text-align:center; color:#6E6E6A; font-size:12.5px;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .wk-statuschip { flex:0 0 auto; background:#F5F5F3; border-radius:99px;
          padding:4px 12px; color:#8A8A86; font-size:11.5px;
          white-space:nowrap; max-width:240px; overflow:hidden;
          text-overflow:ellipsis; }
        .wk-chrome .rec { width:8px; height:8px; border-radius:4px;
          background:#EF4444; animation:wkpulse 1.1s infinite; }
        .wk-screen { flex:1; min-height:0; display:flex; align-items:center;
          justify-content:center; background:#FAFAF8; }
        .wk-screen img, .wk-screen video { max-width:100%; max-height:100%;
          display:block; }
        .wk-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
          width:100%; height:100%; padding:18px; grid-auto-rows:1fr; }
        .wk-grid .beat { border-radius:10px; overflow:hidden; min-height:0;
          background:#0B0B09;
          border:1px solid #E6E6E3; background:#fff; }
        .wk-grid .beat img { width:100%; height:100%; object-fit:contain; }
        .wk-library { display:grid; grid-template-columns:repeat(auto-fill, minmax(260px, 1fr));
          gap:18px; width:100%; height:100%; padding:22px; overflow-y:auto;
          align-content:start; }
        .wk-filmcard { display:flex; flex-direction:column; border-radius:14px;
          overflow:hidden; background:#fff; border:1px solid #E6E6E3;
          text-decoration:none; color:inherit; transition:border-color .15s; }
        .wk-filmcard:hover { border-color:#C9C9C4; }
        .wk-filmcard .prev { aspect-ratio:16/9; background:#0B0B09; }
        .wk-filmcard .prev video { width:100%; height:100%; object-fit:cover;
          display:block; }
        .wk-filmcard .meta { padding:14px 16px 16px; }
        .wk-filmcard .name { font-size:15px; font-weight:650; color:#1B1B1A; }
        .wk-filmcard .sub { font-size:12.5px; color:#8A8A86; margin-top:2px; }
        .wk-filmcard .open { margin-top:12px; text-align:center; font-size:13px;
          padding:7px 0; border:1px solid #E6E6E3; border-radius:99px;
          color:#1B1B1A; }
        .wk-filmcard:hover .open { background:#F5F5F3; }
        .wk-liveprobe { position:absolute; width:1px; height:1px;
          opacity:0; pointer-events:none; }
        .wk-betachip { display:inline-block; vertical-align:3px;
          margin-left:8px; padding:1px 8px; border-radius:99px;
          font-size:10px; font-weight:700; letter-spacing:.08em;
          text-transform:uppercase; color:#3B82F6; background:#EAF1FF; }
        .wk-playerwrap { width:100%; height:100%; display:flex;
          flex-direction:column; gap:10px; padding:14px; min-height:0; }
        .wk-playerwrap video { flex:1; min-height:0; width:100%;
          background:#000; border-radius:10px; object-fit:contain; }
        .wk-timeline { flex:0 0 84px; display:flex; gap:6px; }
        .wk-timeline .seg { flex:1; min-width:0; border-radius:8px;
          overflow:hidden; border:2px solid #E6E6E3; cursor:pointer;
          position:relative; background:#fff; }
        .wk-timeline .seg.on { border-color:#3B82F6; }
        .wk-timeline .seg img { width:100%; height:100%; object-fit:cover; }
        .wk-timeline .seg span { position:absolute; left:0; right:0; bottom:0;
          font-size:9.5px; padding:2px 6px; color:#fff;
          background:linear-gradient(transparent, rgba(0,0,0,0.65));
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .wk-text { max-width:640px; text-align:center; padding:30px; }
        .wk-text .big { font-size:22px; font-weight:650; line-height:1.4; }
        .wk-text .small { color:#8A8A86; margin-top:10px; font-size:13.5px; }
      `}</style>
    </div>,
    document.body,
  )
}
