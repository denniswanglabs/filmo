'use client'
// Walkrec beta workspace — the Ploy-shaped page: ONE white canvas in browser
// chrome where everything happens (page reads, the live recording, the beats,
// the film), and ONE timeline rail on the left merging conversation + work
// updates chronologically. Direct React port of the validated local viewer;
// same event contract, agent_events + storage instead of localhost.
import { useCallback, useEffect, useRef, useState } from 'react'
import { getAgentRun, sendDirectorMessage, type AgentEvent } from '../../actions'

const VERBS: Record<string, string> = {
  read: 'Scouting', decide: 'Framing', film: 'Rolling',
  design: 'Cutting', assemble: 'Printing', review: 'Grading',
}
const THREAD_KINDS = new Set([
  'run.start', 'read.page', 'read.quotes', 'decide.plan', 'decide.guard',
  'film.recording', 'film.shot', 'design.beat', 'review.lint',
  'review.finding', 'review.pass', 'review.apply', 'review.done',
  'assemble.film', 'run.error', 'chat.user', 'chat.director',
])

type LocalMsg = { ts: number; kind: 'user' | 'dir'; text: string }

function reduce(evts: AgentEvent[]) {
  const S = {
    pages: [] as AgentEvent[], plan: [] as string[], beats: [] as AgentEvent[],
    review: [] as AgentEvent[], film: '', filmSeq: 0, phase: 'read',
    status: '', lastTitle: '', site: '', done: false,
  }
  for (const e of evts) {
    const k = e.kind
    if (k === 'run.start') {
      const m = e.title.match(/for (.+)$/)
      if (m) S.site = m[1]
      S.done = false
    }
    if (k === 'read.page') { S.pages.push(e); S.phase = 'read' }
    if (k === 'decide.plan') { S.plan = e.detail.split('\n'); S.phase = 'decide' }
    if (k.startsWith('film.')) S.phase = 'film'
    if (k === 'design.beat' && e.artifact_url) { S.beats.push(e); S.phase = 'design' }
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
  const [localMsgs, setLocalMsgs] = useState<LocalMsg[]>([])
  const [input, setInput] = useState('')
  const [pinned, setPinned] = useState<AgentEvent | null>(null)
  const phaseStart = useRef(Date.now())
  const lastPhase = useRef('')
  const threadRef = useRef<HTMLDivElement>(null)
  const evtsRef = useRef<AgentEvent[]>([])

  const S = reduce(evts)

  // Event poll (1.5s) — the same contract as the local viewer.
  useEffect(() => {
    let stop = false
    const tick = async () => {
      if (stop) return
      try {
        const after = evtsRef.current.length
          ? evtsRef.current[evtsRef.current.length - 1].seq : -1
        const res = await getAgentRun(runKey, after, (await getToken()) || '')
        if (!('error' in res) && res.events.length) {
          evtsRef.current = [...evtsRef.current, ...res.events]
          setEvts(evtsRef.current)
        }
      } catch { /* transient */ }
      setTimeout(tick, 1500)
    }
    tick()
    return () => { stop = true }
  }, [runKey, getToken])

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
    const res = await sendDirectorMessage(runKey, text, (await getToken()) || '')
    if ('error' in res) {
      setLocalMsgs((m) => [...m, {
        ts: Date.now() / 1000, kind: 'dir',
        text: 'That did not go through — try again.',
      }])
    }
  }, [input, runKey, getToken])

  // Merge thread items chronologically; server chat events replace local echoes.
  const items: Array<
    | { ts: number; type: 'user' | 'dir'; text: string }
    | { ts: number; type: 'work'; e: AgentEvent }
  > = []
  for (const e of evts) {
    if (!THREAD_KINDS.has(e.kind)) continue
    if (e.kind === 'chat.user') items.push({ ts: e.ts, type: 'user', text: e.title })
    else if (e.kind === 'chat.director') items.push({ ts: e.ts, type: 'dir', text: e.title })
    else items.push({ ts: e.ts, type: 'work', e })
  }
  for (const m of localMsgs) {
    const dupe = evts.some((e) =>
      (e.kind === 'chat.user' || e.kind === 'chat.director')
      && e.title === m.text && Math.abs(e.ts - m.ts) < 60)
    if (!dupe) items.push({ ts: m.ts, type: m.kind, text: m.text })
  }
  items.sort((a, b) => a.ts - b.ts)

  const working = !S.done
  const verb = VERBS[S.phase] || 'Working'
  const elapsed = Math.round((Date.now() - phaseStart.current) / 1000)

  // The ONE screen's content.
  let screen: React.ReactNode = null
  let pill = ''
  const lastPage = S.pages[S.pages.length - 1]
  if (pinned) {
    screen = <img src={pinned.artifact_url} alt="" />
    pill = pinned.title
  } else if (liveFresh && working) {
    screen = (
      <img src={`${liveUrl}&t=${liveTick}`} alt=""
        onError={() => setLiveFresh(false)} />
    )
    pill = `Recording ${S.site || ''}`
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
    screen = (
      <div className="wk-grid">
        {S.beats.map((b) => (
          <div key={b.seq} className="beat"><img src={b.artifact_url} alt="" /></div>
        ))}
      </div>
    )
    pill = S.phase === 'review' ? 'Grading — story and coherence' : 'Cutting — beat by beat'
  } else {
    screen = S.film
      ? <video src={S.film} controls muted />
      : <div className="wk-text"><div className="big">{S.status === 'failed' ? 'The run failed.' : 'Finished.'}</div></div>
    pill = S.film ? `film · ${S.review.length ? 'review passed' : 'final'}` : ''
  }

  // Live-frame freshness: try turning it on whenever working (img onError flips off).
  useEffect(() => {
    if (working && liveUrl) setLiveFresh(true)
  }, [liveTick, working, liveUrl])

  return (
    <div className="wk-root">
      <div className="wk-rail">
        <div className="wk-railhead">
          <div className="wk-blob" />
          <div>
            <h1>Filmo Director</h1>
            <div className="sub">{S.done ? (S.status || 'finished') : 'live'}</div>
          </div>
        </div>
        <div className="wk-thread" ref={threadRef}>
          {items.map((it, i) => {
            if (it.type !== 'work') {
              return it.type === 'user'
                ? <div key={i} className="t-user">{it.text}</div>
                : <div key={i} className="t-dir">{it.text}</div>
            }
            const e = it.e
            const thumb = e.artifact_url && !e.artifact_url.includes('.mp4')
            return (
              <div key={i} className="t-work">
                {thumb ? (
                  <img src={e.artifact_url} alt=""
                    onClick={() => { setPinned(e); setTimeout(() => setPinned(null), 8000) }} />
                ) : null}
                <div>
                  <b>{e.title}</b>
                  {e.detail ? <><br />{e.detail.split('\n')[0].slice(0, 90)}</> : null}
                </div>
              </div>
            )
          })}
          {working ? (
            <div className="t-verb"><span className="dotp" />{verb}… {elapsed}s</div>
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
            <div className="pill">{pill}</div>
            {liveFresh && working ? <div className="rec" /> : null}
          </div>
          <div className="wk-screen">{screen}</div>
        </div>
      </div>
      <style>{`
        .wk-root { position:fixed; inset:0; display:flex; background:#F1F1EF;
          color:#1B1B1A; font:14px/1.5 Inter,-apple-system,sans-serif; z-index:50; }
        .wk-rail { flex:0 0 380px; display:flex; flex-direction:column;
          border-right:1px solid #E6E6E3; }
        .wk-railhead { flex:0 0 62px; display:flex; align-items:center; gap:12px;
          padding:0 20px; }
        .wk-railhead h1 { font-size:14.5px; font-weight:700; margin:0; }
        .wk-railhead .sub { color:#8A8A86; font-size:12px; }
        .wk-blob { width:36px; height:36px; position:relative; flex-shrink:0;
          background:radial-gradient(circle at 32% 30%, #7FB0FF, #3B82F6 58%, #1D4ED8);
          animation:wkmorph 3.2s ease-in-out infinite, wkspin 8s linear infinite; }
        .wk-blob::after { content:""; position:absolute; width:34%; height:34%;
          right:16%; top:26%; background:#fff; border-radius:50%;
          animation:wkhole 3.2s ease-in-out infinite; }
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
        .wk-canvaswrap { flex:1; min-width:0; display:flex; align-items:center;
          justify-content:center; padding:26px; }
        .wk-canvas { width:100%; max-width:1100px; height:100%; max-height:760px;
          background:#fff; border-radius:16px; display:flex; flex-direction:column;
          overflow:hidden; box-shadow:0 1px 2px rgba(0,0,0,0.04),
          0 24px 70px -30px rgba(0,0,0,0.18); }
        .wk-chrome { flex:0 0 44px; display:flex; align-items:center; gap:14px;
          padding:0 16px; border-bottom:1px solid #E6E6E3; }
        .wk-chrome .dots { display:flex; gap:6px; }
        .wk-chrome .dots i { width:10px; height:10px; border-radius:5px;
          background:#E4E4E1; }
        .wk-chrome .pill { flex:1; max-width:560px; margin:0 auto;
          background:#F5F5F3; border-radius:8px; padding:5px 14px;
          text-align:center; color:#8A8A86; font-size:12.5px;
          white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .wk-chrome .rec { width:8px; height:8px; border-radius:4px;
          background:#EF4444; animation:wkpulse 1.1s infinite; }
        .wk-screen { flex:1; min-height:0; display:flex; align-items:center;
          justify-content:center; background:#FAFAF8; }
        .wk-screen img, .wk-screen video { max-width:100%; max-height:100%;
          display:block; }
        .wk-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
          width:100%; height:100%; padding:18px; grid-auto-rows:1fr; }
        .wk-grid .beat { border-radius:10px; overflow:hidden; min-height:0;
          border:1px solid #E6E6E3; background:#fff; }
        .wk-grid .beat img { width:100%; height:100%; object-fit:cover; }
        .wk-text { max-width:640px; text-align:center; padding:30px; }
        .wk-text .big { font-size:22px; font-weight:650; line-height:1.4; }
        .wk-text .small { color:#8A8A86; margin-top:10px; font-size:13.5px; }
      `}</style>
    </div>
  )
}
