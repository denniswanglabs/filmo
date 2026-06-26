'use client'

// EditorDemo — a self-contained, looping "editor in use" product demo. It is a
// FAUX editor (no real editor mounted, no heavy deps) that mirrors the Filmo
// editor at app/runs/[id]/edit/ — same vocabulary so the demo reads as ACCURATE:
//   • top chrome: Back chip · Filmo wordmark + EDITOR tag · "Editing ● Ready"
//     status (green dot) · Saved indicator · blue Export button
//   • left rail: LIVE PREVIEW pill + format meta (16:9 · 1920×1080 / 5 scenes /
//     30s · 30fps) + the dark #0B0F1A stage (kicker / heading / subtitle)
//   • inspector (white #F7F9FC): "Inspector" + "5 SCENES" header, the selected-
//     scene chip, a GEOMETRY section of labelled sliders with value pills
//     (Title size / Subtitle size / Plate width) and a TEXT section "Title" field
//   • bottom: a blue timeline of solid Scene 1…5 blocks + a glowing playhead
//
// THE LOOP (~12s, ALL beats driven off ONE shared timeline so the cursor, the
// control it touches, the value pill, and the preview move in LOCKSTEP and the
// SAME DIRECTION — drag right = bigger = heading grows). Beats:
//   1. cursor → TIMELINE, clicks "Scene 2" (click pulse + brighten)
//   2. cursor → "Title size" slider, DRAGS handle RIGHT → handle + blue fill +
//      value pill (92→150) + preview HEADING all grow together, left-to-right
//   3. cursor → "Subtitle size" slider, nudges → preview SUBTITLE grows in sync
//   4. cursor → "Title" TEXT field → blinking caret, heading crossfades
//      "Ship faster." → "Ship today." (as if typed)
//   5. brief settle, then everything eases back to the start (no teleport)
// The playhead sweeps the timeline gently throughout. The cursor is a small arrow
// SVG with a white stroke; it scales down slightly on each click / drag-grab.
//
// Pure CSS keyframes (transform / opacity / width only — GPU-composited), no JS
// state. `prefers-reduced-motion` freezes a clean, legible mid-edit static frame
// with NO animation.

import { Reveal } from './Motion'
import { useEffect, useState } from 'react'

// Beat 4 title edit — char-by-char at ~60 wpm (60*5 keystrokes/min = 5/s = 200ms
// each): hold "Ship faster." → backspace to "Ship " → type "Ship today." → hold →
// reset. Driven off the same mount clock as the 12s CSS loop so the cursor (CSS)
// and the text (JS) stay in sync; mirrored in BOTH the inspector field and the
// video heading.
const ED_FULL = 'Ship faster.'
const ED_STEM = 'Ship '
const ED_TYPED = 'Ship today.'
const ED_CHAR_MS = 200
const ED_LOOP_MS = 12000
const ED_DEL_START = 7920 // 66% of the loop — when the cursor reaches the Title field
const ED_DEL_END = ED_DEL_START + (ED_FULL.length - ED_STEM.length) * ED_CHAR_MS
const ED_TYPE_END = ED_DEL_END + (ED_TYPED.length - ED_STEM.length) * ED_CHAR_MS

function edTitleAt(t: number): string {
  if (t < ED_DEL_START) return ED_FULL
  if (t < ED_DEL_END) {
    const removed = Math.floor((t - ED_DEL_START) / ED_CHAR_MS)
    return ED_FULL.slice(0, ED_FULL.length - removed)
  }
  if (t < ED_TYPE_END) {
    const added = Math.floor((t - ED_DEL_END) / ED_CHAR_MS)
    return ED_TYPED.slice(0, ED_STEM.length + added)
  }
  return ED_TYPED
}

export default function EditorDemo() {
  // The live title text, shown in both the inspector field and the video heading.
  const [titleText, setTitleText] = useState(ED_FULL)
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setTitleText(ED_FULL) // matches the frozen mid-drag (pre-edit) reduced frame
      return
    }
    // Date.now()-based so the text stays correctly timed even if the interval is
    // throttled; setState bails out when the char hasn't changed (no churn).
    const start = Date.now()
    const id = setInterval(() => {
      const next = edTitleAt((Date.now() - start) % ED_LOOP_MS)
      setTitleText((prev) => (prev === next ? prev : next))
    }, 80)
    return () => clearInterval(id)
  }, [])

  return (
    <section id="editor-demo" className="panel panel--lit px-5 py-20 sm:py-24">
      {/* Blue glass top edge — our signature on the rounded panel lip. */}
      <span aria-hidden="true" className="panel__edge" />
      <div className="mx-auto max-w-5xl">
        {/* Section header */}
        <Reveal className="mx-auto max-w-xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight text-[#0E1320] sm:text-4xl">
            Yours to fine-tune.
          </h2>
          <p className="mx-auto mt-3 text-[#5A6472]">
            Every cut ships as structured, editable scenes — drag a headline bigger,
            nudge the subtitle, or retype the copy and watch the preview update live.
            No timeline wrangling, no re-render wait.
          </p>
        </Reveal>

        {/* The faux editor */}
        <Reveal className="mt-12">
          <div className="ed mx-auto w-full max-w-4xl select-none overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_30px_80px_-40px_rgba(30,58,120,0.32)] ring-1 ring-inset ring-[#EAF1FF]">
            {/* ============================================ TOP CHROME BAR */}
            <div className="flex items-center gap-2.5 border-b border-[#E6EAF0] bg-white px-3.5 py-2.5 sm:gap-3">
              {/* Back chip */}
              <span className="inline-flex items-center gap-1 rounded-lg border border-[#E6EAF0] bg-[#F7F9FC] px-2 py-1 text-[11px] font-semibold text-[#5A6472]">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M14 6l-6 6 6 6" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Back
              </span>
              <span aria-hidden="true" className="h-5 w-px bg-[#E6EAF0]" />
              {/* Filmo wordmark + EDITOR tag */}
              <span className="inline-flex items-center gap-2">
                <svg width="18" height="18" viewBox="14 13 56 56" aria-hidden="true" className="block">
                  <path
                    fillRule="evenodd"
                    fill="#3B82F6"
                    d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
                  />
                </svg>
                <span className="text-[15px] font-bold tracking-tight text-[#0E1320]">Filmo</span>
                <span className="rounded-md border border-[#E6EAF0] px-1.5 py-[2px] text-[9px] font-bold uppercase tracking-[0.14em] text-[#5A6472]">
                  Editor
                </span>
              </span>
              <span aria-hidden="true" className="hidden h-5 w-px bg-[#E6EAF0] sm:block" />
              {/* Editing ● Ready status (green dot) */}
              <span className="hidden items-center gap-1.5 text-[11px] text-[#5A6472] sm:inline-flex">
                <span className="h-[7px] w-[7px] rounded-full bg-[#22C55E]" />
                <span className="font-semibold uppercase tracking-wide text-[#8A94A6]">Editing</span>
                Ready
              </span>

              <span className="ml-auto inline-flex items-center gap-2">
                {/* Saved indicator */}
                <span className="hidden items-center gap-1.5 rounded-lg border border-[#E6EAF0] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#5A6472] sm:inline-flex">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M5 12.5l4.5 4.5L19 7" stroke="#22C55E" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Saved
                </span>
                {/* Export button (blue) */}
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-[#3B82F6] px-3 py-1.5 text-[11px] font-bold text-white shadow-[0_4px_12px_-2px_rgba(59,130,246,0.5)]">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 15V4m0 0L8 8m4-4l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M5 14v4a2 2 0 002 2h10a2 2 0 002-2v-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  Export
                </span>
              </span>
            </div>

            {/* ===================== BODY: left rail (stage) + inspector ===== */}
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_268px]">
              {/* ----------------------------------- LEFT RAIL: live preview */}
              <div className="bg-white p-3.5 sm:p-4">
                {/* LIVE PREVIEW pill + format meta */}
                <div className="mb-3 flex flex-wrap items-center gap-1.5">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[#BFD8FF] bg-[#EAF2FF] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-[#2563EB]">
                    <span className="ed-livedot h-1.5 w-1.5 rounded-full bg-[#3B82F6]" />
                    Live preview
                  </span>
                  <span className="rounded-full border border-[#E6EAF0] bg-[#F7F9FC] px-2.5 py-1 text-[10px] font-semibold text-[#5A6472]">
                    16:9 · 1920×1080
                  </span>
                  <span className="hidden rounded-full border border-[#E6EAF0] bg-[#F7F9FC] px-2.5 py-1 text-[10px] font-semibold text-[#5A6472] sm:inline">
                    5 scenes
                  </span>
                  <span className="rounded-full border border-[#E6EAF0] bg-[#F7F9FC] px-2.5 py-1 text-[10px] font-semibold text-[#5A6472]">
                    30s · 30fps
                  </span>
                </div>

                {/* DARK VIDEO STAGE — kicker / heading / subtitle scale live */}
                <div className="relative grid aspect-video place-items-center overflow-hidden rounded-xl bg-[#0B0F1A] px-6 shadow-[inset_0_0_0_1px_rgba(14,19,32,0.5)]">
                  {/* faint stage grid for depth */}
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-0 opacity-[0.10]"
                    style={{
                      backgroundImage:
                        'linear-gradient(#3B82F6 1px, transparent 1px), linear-gradient(90deg, #3B82F6 1px, transparent 1px)',
                      backgroundSize: '32px 32px',
                    }}
                  />
                  <div className="relative w-full text-center">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-[#60A5FA]">
                      Scene 02
                    </p>
                    {/* heading scales live with the Title-size drag; the text node
                        crossfades to the "typed" word in beat 4 via ::after. */}
                    <h3 className="ed-headline relative inline-block font-semibold leading-[1.05] text-white">
                      {titleText}
                    </h3>
                    {/* subtitle scales live with the Subtitle-size nudge */}
                    <p className="ed-subtitle mx-auto mt-3 max-w-[24ch] font-medium leading-snug text-[#9FB2D4]">
                      Turn any landing page into a launch film.
                    </p>
                  </div>
                </div>
              </div>

              {/* ----------------------------------------------- INSPECTOR */}
              <div className="border-t border-[#E6EAF0] bg-[#F7F9FC] p-3.5 sm:border-l sm:border-t-0 sm:p-4">
                {/* Inspector header */}
                <div className="mb-3 flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="text-[#3B82F6]">
                    <path d="M4 7h10M18 7h2M4 17h2M10 17h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    <circle cx="16" cy="7" r="2.4" stroke="currentColor" strokeWidth="1.8" />
                    <circle cx="8" cy="17" r="2.4" stroke="currentColor" strokeWidth="1.8" />
                  </svg>
                  <span className="text-[12px] font-extrabold tracking-tight text-[#0E1320]">Inspector</span>
                  <span className="ml-auto text-[9.5px] font-bold uppercase tracking-[0.12em] text-[#8A94A6]">
                    5 scenes
                  </span>
                </div>

                {/* Selected-scene chip */}
                <div className="mb-3.5 flex items-center gap-2.5 rounded-xl border border-[#BFD8FF] bg-[#EAF2FF] px-3 py-2.5">
                  <span className="grid h-8 w-8 flex-none place-items-center rounded-lg border border-[#BFD8FF] bg-white text-[#3B82F6]">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
                      <path d="M3 9h18M3 15h18M8 4v16M16 4v16" stroke="currentColor" strokeWidth="1.3" />
                    </svg>
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[9px] font-bold uppercase tracking-[0.12em] text-[#5A6472]">
                      Editing scene 02 of 05
                    </span>
                    <span className="block font-mono text-[12px] font-bold text-[#0E1320]">hero title</span>
                  </span>
                </div>

                {/* GEOMETRY section */}
                <p className="mb-2.5 flex items-center gap-1.5 text-[9.5px] font-bold uppercase tracking-[0.16em] text-[#8A94A6]">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M4 7h10M18 7h2M4 17h2M10 17h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    <circle cx="16" cy="7" r="2.4" stroke="currentColor" strokeWidth="1.8" />
                    <circle cx="8" cy="17" r="2.4" stroke="currentColor" strokeWidth="1.8" />
                  </svg>
                  Geometry
                </p>

                {/* Title size slider — the one the cursor DRAGS */}
                <div className="ed-slider mb-3" data-which="title">
                  <div className="mb-1.5 flex items-baseline justify-between">
                    <span className="text-[11px] font-medium text-[#5A6472]">Title size</span>
                    <span className="ed-pill ed-pill--title relative inline-block rounded-full border border-[#BFD8FF] bg-[#EAF2FF] px-2 py-[1.5px] text-[11px] font-bold tabular-nums text-[#2563EB]">
                      <span className="ed-pill__a">92</span>
                      <span aria-hidden="true" className="ed-pill__b absolute inset-0 grid place-items-center">150</span>
                    </span>
                  </div>
                  <div className="relative h-1.5 rounded-full bg-[#E3E9F2]">
                    <span className="ed-fill ed-fill--title absolute inset-y-0 left-0 rounded-full bg-[#3B82F6]" />
                    <span className="ed-handle ed-handle--title absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#3B82F6] bg-white shadow-[0_1px_4px_rgba(37,99,235,0.45)]" />
                  </div>
                </div>

                {/* Subtitle size slider — the one the cursor NUDGES */}
                <div className="ed-slider mb-3" data-which="sub">
                  <div className="mb-1.5 flex items-baseline justify-between">
                    <span className="text-[11px] font-medium text-[#5A6472]">Subtitle size</span>
                    <span className="ed-pill ed-pill--sub relative inline-block rounded-full border border-[#BFD8FF] bg-[#EAF2FF] px-2 py-[1.5px] text-[11px] font-bold tabular-nums text-[#2563EB]">
                      <span className="ed-pill__a">34</span>
                      <span aria-hidden="true" className="ed-pill__b absolute inset-0 grid place-items-center">44</span>
                    </span>
                  </div>
                  <div className="relative h-1.5 rounded-full bg-[#E3E9F2]">
                    <span className="ed-fill ed-fill--sub absolute inset-y-0 left-0 rounded-full bg-[#3B82F6]" />
                    <span className="ed-handle ed-handle--sub absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#3B82F6] bg-white shadow-[0_1px_4px_rgba(37,99,235,0.45)]" />
                  </div>
                </div>

                {/* Plate width slider — static (context, not driven) */}
                <div className="mb-4">
                  <div className="mb-1.5 flex items-baseline justify-between">
                    <span className="text-[11px] font-medium text-[#5A6472]">Plate width</span>
                    <span className="rounded-full border border-[#E6EAF0] bg-white px-2 py-[1.5px] text-[11px] font-bold tabular-nums text-[#5A6472]">
                      1200
                    </span>
                  </div>
                  <div className="relative h-1.5 rounded-full bg-[#E3E9F2]">
                    <span className="absolute inset-y-0 left-0 w-[70%] rounded-full bg-[#C7D6EC]" />
                    <span className="absolute top-1/2 left-[70%] h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#C7D6EC] bg-white" />
                  </div>
                </div>

                {/* TEXT section — the "Title" field the cursor types into */}
                <p className="mb-2 flex items-center gap-1.5 text-[9.5px] font-bold uppercase tracking-[0.16em] text-[#8A94A6]">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M5 7V5h14v2M12 5v14M9 19h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Text
                </p>
                <span className="mb-1 block text-[10.5px] font-semibold text-[#5A6472]">Title</span>
                <div className="ed-field relative flex items-center rounded-lg border border-[#D4E2FB] bg-white px-2.5 py-2 text-[12px] font-medium text-[#0E1320]">
                  <span>{titleText}</span>
                  <span aria-hidden="true" className="ed-caret ml-[1px] inline-block h-[14px] w-[1.5px] bg-[#3B82F6]" />
                </div>
              </div>
            </div>

            {/* ============== BLUE TIMELINE — Scene 1…5 blocks + playhead ==== */}
            <div className="relative border-t border-[#E6EAF0] bg-white px-3.5 py-3 sm:px-4">
              <div className="mb-2 flex items-center gap-1.5">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="text-[#3B82F6]">
                  <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M3 9h18M3 15h18M8 4v16M16 4v16" stroke="currentColor" strokeWidth="1.3" />
                </svg>
                <span className="text-[9.5px] font-bold uppercase tracking-[0.16em] text-[#5A6472]">Timeline</span>
              </div>
              <div className="relative flex h-9 gap-1.5">
                {[1, 2, 3, 4, 5].map((n) => (
                  <div
                    key={n}
                    className={
                      n === 2
                        ? 'ed-clip ed-clip--sel relative grid flex-1 place-items-center rounded-md bg-[#3B82F6] text-[11px] font-bold text-white ring-2 ring-[#2563EB]'
                        : 'grid flex-1 place-items-center rounded-md bg-[#3B82F6]/70 text-[11px] font-bold text-white'
                    }
                  >
                    Scene {n}
                  </div>
                ))}
                {/* live playhead sweeping the timeline */}
                <span
                  aria-hidden="true"
                  className="ed-playhead absolute top-0 bottom-0 w-0.5 rounded bg-[#3B82F6]"
                  style={{ boxShadow: '0 0 8px 1px rgba(59,130,246,0.55)' }}
                />
              </div>
            </div>

            {/* ===================== THE ANIMATED CURSOR (arrow SVG) ======== */}
            <span aria-hidden="true" className="ed-cursor">
              <svg viewBox="0 0 24 24" width="22" height="22">
                <path
                  d="M5 3 L5 19 L9.5 14.5 L12.5 21 L15 20 L12 13.5 L18 13.5 Z"
                  fill="#0E1320"
                  stroke="#FFFFFF"
                  strokeWidth="1.2"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
          </div>
        </Reveal>
      </div>

      <style jsx>{`
        /* ==================================================================
           ONE shared 12s timeline drives every beat in lockstep.
           Beat map (% of the loop):
             0–8     settle (rest frame)
             8–18    BEAT 1  cursor → timeline, click "Scene 2"
             18–42   BEAT 2  cursor → Title-size slider, DRAG right (92→150)
             42–58   BEAT 3  cursor → Subtitle-size slider, nudge (34→44)
             58–80   BEAT 4  cursor → Title text field, type → heading swaps
             80–100  BEAT 5  settle, then ease everything back to start
           ================================================================== */
        .ed {
          position: relative;
        }
        :global(.ed *) {
          box-sizing: border-box;
        }

        /* -------------------------------------------------- PREVIEW HEADING */
        /* Base font-size; transform-scale does the live growth so it stays GPU
           composited. Grows during the Title-size DRAG (beat 2), holds, then
           eases back during the reset. transform-origin:bottom so it grows up
           from the subtitle (left-to-right reads natural with the drag). */
        .ed-headline {
          font-size: clamp(1.7rem, 4.6vw, 3rem);
          transform-origin: center bottom;
          animation: ed-head-scale 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-head-scale {
          0%,
          20% {
            transform: scale(0.78);
          }
          /* drag right = bigger, in sync with the slider fill growing. HOLD full
             size through the beat-4 type (which finishes at ~88% of the loop) so
             the heading never shrinks mid-typing — only reset AFTER typing lands. */
          42%,
          88% {
            transform: scale(1.16);
          }
          97%,
          100% {
            transform: scale(0.78);
          }
        }
        /* heading text is JS-driven (char-by-char in beat 4) — no CSS crossfade. */

        /* -------------------------------------------------- PREVIEW SUBTITLE */
        .ed-subtitle {
          font-size: clamp(0.72rem, 1.5vw, 0.95rem);
          transform-origin: center top;
          animation: ed-sub-scale 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-sub-scale {
          0%,
          48% {
            transform: scale(1);
          }
          /* nudge in beat 3 (42–58) -> subtitle grows; hold through the type so the
             whole preview stays steady until typing finishes (~88%). */
          58%,
          88% {
            transform: scale(1.22);
          }
          97%,
          100% {
            transform: scale(1);
          }
        }

        /* ------------------------------------------------------ TITLE SLIDER */
        /* The fill + handle grow LEFT→RIGHT during the drag (beat 2), exactly
           tracking the cursor and the heading scale. Rest 30% -> 86%. */
        .ed-fill--title {
          width: 30%;
          animation: ed-title-fill 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-title-fill {
          0%,
          20% {
            width: 30%;
          }
          42%,
          82% {
            width: 86%;
          }
          96%,
          100% {
            width: 30%;
          }
        }
        .ed-handle--title {
          left: 30%;
          animation: ed-title-handle 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-title-handle {
          0%,
          20% {
            left: 30%;
            transform: translate(-50%, -50%) scale(1);
          }
          /* grab pop as the cursor presses down on the handle */
          24% {
            transform: translate(-50%, -50%) scale(1.32);
          }
          42%,
          82% {
            left: 86%;
            transform: translate(-50%, -50%) scale(1.18);
          }
          96%,
          100% {
            left: 30%;
            transform: translate(-50%, -50%) scale(1);
          }
        }
        /* value pill 92 -> 150 crossfade, lands when the drag completes */
        .ed-pill--title .ed-pill__b {
          opacity: 0;
          animation: ed-title-pillb 12s steps(1, end) infinite;
        }
        @keyframes ed-title-pillb {
          0%,
          40% {
            opacity: 0;
          }
          41%,
          92% {
            opacity: 1;
          }
          94%,
          100% {
            opacity: 0;
          }
        }
        .ed-pill--title .ed-pill__a {
          animation: ed-title-pilla 12s steps(1, end) infinite;
        }
        @keyframes ed-title-pilla {
          0%,
          40% {
            opacity: 1;
          }
          41%,
          92% {
            opacity: 0;
          }
          94%,
          100% {
            opacity: 1;
          }
        }

        /* --------------------------------------------------- SUBTITLE SLIDER */
        .ed-fill--sub {
          width: 32%;
          animation: ed-sub-fill 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-sub-fill {
          0%,
          52% {
            width: 32%;
          }
          58%,
          82% {
            width: 60%;
          }
          96%,
          100% {
            width: 32%;
          }
        }
        .ed-handle--sub {
          left: 32%;
          animation: ed-sub-handle 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-sub-handle {
          0%,
          52% {
            left: 32%;
            transform: translate(-50%, -50%) scale(1);
          }
          53% {
            transform: translate(-50%, -50%) scale(1.3);
          }
          58%,
          82% {
            left: 60%;
            transform: translate(-50%, -50%) scale(1.14);
          }
          96%,
          100% {
            left: 32%;
            transform: translate(-50%, -50%) scale(1);
          }
        }
        .ed-pill--sub .ed-pill__b {
          opacity: 0;
          animation: ed-sub-pillb 12s steps(1, end) infinite;
        }
        @keyframes ed-sub-pillb {
          0%,
          55% {
            opacity: 0;
          }
          56%,
          92% {
            opacity: 1;
          }
          94%,
          100% {
            opacity: 0;
          }
        }
        .ed-pill--sub .ed-pill__a {
          animation: ed-sub-pilla 12s steps(1, end) infinite;
        }
        @keyframes ed-sub-pilla {
          0%,
          55% {
            opacity: 1;
          }
          56%,
          92% {
            opacity: 0;
          }
          94%,
          100% {
            opacity: 1;
          }
        }

        /* --------------------------------------------------- TITLE TEXT FIELD */
        /* Blinking text caret in the inspector Title field (field text is JS-driven). */
        .ed-caret {
          animation: ed-blink 1s steps(1, end) infinite;
        }
        @keyframes ed-blink {
          0%,
          50% {
            opacity: 1;
          }
          51%,
          100% {
            opacity: 0;
          }
        }

        /* --------------------------------------------- SELECTED CLIP (beat 1) */
        /* Scene 2 is the selected clip; on the beat-1 click it pulses brighter. */
        .ed-clip--sel {
          animation: ed-clip-pulse 12s ease-out infinite;
        }
        @keyframes ed-clip-pulse {
          0%,
          9% {
            box-shadow: 0 0 0 0 rgba(37, 99, 235, 0);
            filter: brightness(0.92);
          }
          12% {
            box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.35);
            filter: brightness(1.12);
          }
          16% {
            box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
            filter: brightness(1);
          }
          100% {
            filter: brightness(1);
          }
        }

        /* ----------------------------------------------------- LIVE-DOT pulse */
        .ed-livedot {
          animation: ed-livedot 1.8s ease-in-out infinite;
        }
        @keyframes ed-livedot {
          0%,
          100% {
            opacity: 1;
          }
          50% {
            opacity: 0.35;
          }
        }

        /* ----------------------------------------------------- THE CURSOR */
        /* Natural path: starts mid-stage, drops to the TIMELINE (Scene 2),
           rises to the Title-size HANDLE and tracks it RIGHT during the drag,
           drops to the Subtitle handle, then moves to the Title text FIELD.
           Percentages are relative to the .ed container box. Scales down on
           each click / grab. Single closed loop — returns to the start. */
        /* Positions are MEASURED against the rendered editor (ed 896x538): the
           cursor's tip lands ON each control. Title knob top ~40.8%, subtitle knob
           ~49.2%, text field ~72.4%, Scene 2 block at left ~30.6%. */
        /* The cursor ENTERS from the top-right corner (fades in) and EXITS to the
           top-right corner (fades out) — it never rests mid-stage. The card is
           overflow-hidden, so the corner anchor sits just inside the top-right. */
        .ed-cursor {
          position: absolute;
          top: 5%;
          left: 92%;
          opacity: 0;
          z-index: 20;
          pointer-events: none;
          filter: drop-shadow(0 2px 4px rgba(14, 19, 32, 0.3));
          animation: ed-cursor 12s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
        @keyframes ed-cursor {
          /* enter from the top-right corner, fading in */
          0% {
            top: 5%;
            left: 92%;
            opacity: 0;
            transform: scale(1);
          }
          4% {
            top: 5%;
            left: 92%;
            opacity: 1;
            transform: scale(1);
          }
          /* BEAT 1 — down to the timeline, onto Scene 2 (30.6%, 94.2%) */
          9% {
            top: 94%;
            left: 30%;
            transform: scale(1);
          }
          11% {
            transform: scale(0.8);
          }
          14% {
            transform: scale(1);
          }
          /* BEAT 2 — onto the Title-size knob at its rest (79.7%, 40.8%) */
          20% {
            top: 40%;
            left: 79%;
            transform: scale(1);
          }
          23% {
            transform: scale(0.8);
          }
          /* drag the knob RIGHT to 86% pos (94.4%) — cursor tracks it exactly */
          42% {
            top: 40%;
            left: 94%;
            transform: scale(0.8);
          }
          45% {
            transform: scale(1);
          }
          /* BEAT 3 — onto the Subtitle knob (80.3%, 49.2%), nudge to 60% (87.6%) */
          52% {
            top: 49%;
            left: 80%;
            transform: scale(1);
          }
          54% {
            transform: scale(0.8);
          }
          58% {
            top: 49%;
            left: 87%;
            transform: scale(0.8);
          }
          60% {
            transform: scale(1);
          }
          /* BEAT 4 — onto the Title text field (85%, 72.4%) */
          66% {
            top: 72%;
            left: 84%;
            transform: scale(1);
          }
          68% {
            transform: scale(0.8);
          }
          70% {
            transform: scale(1);
          }
          /* HOLD at the field, fully opaque, until the typing finishes (~88%) */
          88% {
            top: 72%;
            left: 84%;
            opacity: 1;
            transform: scale(1);
          }
          /* BEAT 5 — exit back up to the top-right corner, fading out */
          96% {
            opacity: 0.35;
          }
          100% {
            top: 5%;
            left: 92%;
            opacity: 0;
            transform: scale(1);
          }
        }

        /* ------------------------------------------------------ PLAYHEAD */
        /* PARKED on Scene 2 — the demo only ever edits Scene 2, so the playhead
           stays on it instead of sweeping around (which read as noise). */
        .ed-playhead {
          left: 30%;
        }

        /* ==================================================================
           REDUCED MOTION — freeze a clean, legible MID-EDIT static frame.
           Title size already at 150 (dragged), heading enlarged, value pills
           showing the new numbers, cursor parked on the Title-size handle.
           No animation at all.
           ================================================================== */
        @media (prefers-reduced-motion: reduce) {
          .ed-headline,
          .ed-headline__a,
          .ed-headline__b,
          .ed-subtitle,
          .ed-fill--title,
          .ed-handle--title,
          .ed-pill--title .ed-pill__a,
          .ed-pill--title .ed-pill__b,
          .ed-fill--sub,
          .ed-handle--sub,
          .ed-pill--sub .ed-pill__a,
          .ed-pill--sub .ed-pill__b,
          .ed-caret,
          .ed-field__a,
          .ed-field__b,
          .ed-clip--sel,
          .ed-livedot,
          .ed-cursor,
          .ed-playhead {
            animation: none !important;
          }
          /* heading enlarged + showing the original word */
          .ed-headline {
            transform: scale(1.12);
          }
          .ed-headline__b {
            opacity: 0;
          }
          .ed-headline__a {
            opacity: 1;
          }
          /* subtitle at rest size */
          .ed-subtitle {
            transform: scale(1);
          }
          /* title slider mid-drag at the new value */
          .ed-fill--title {
            width: 86%;
          }
          .ed-handle--title {
            left: 86%;
            transform: translate(-50%, -50%) scale(1);
          }
          .ed-pill--title .ed-pill__a {
            opacity: 0;
          }
          .ed-pill--title .ed-pill__b {
            opacity: 1;
          }
          /* subtitle slider at rest */
          .ed-fill--sub {
            width: 32%;
          }
          .ed-handle--sub {
            left: 32%;
            transform: translate(-50%, -50%) scale(1);
          }
          .ed-pill--sub .ed-pill__a {
            opacity: 1;
          }
          .ed-pill--sub .ed-pill__b {
            opacity: 0;
          }
          /* field shows original text, no caret */
          .ed-field__a {
            opacity: 1;
          }
          .ed-field__b {
            opacity: 0;
          }
          .ed-caret {
            opacity: 0;
          }
          /* cursor parked on the Title-size knob (dragged position), fully visible */
          .ed-cursor {
            top: 40%;
            left: 94%;
            opacity: 1;
            transform: scale(1);
          }
          .ed-playhead {
            left: 30%;
          }
          .ed-livedot {
            opacity: 1;
          }
        }
      `}</style>
    </section>
  )
}
