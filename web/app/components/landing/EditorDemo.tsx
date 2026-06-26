'use client'

// EditorDemo — a self-contained, looping "editor in use" product demo. It is a
// FAUX editor (no real editor mounted, no heavy deps) that mirrors the Filmo
// editor's NEW look: white/neutral chrome, ink #0E1320 text, a single restrained
// blue accent (#3B82F6), a dark video stage, and a blue timeline with white
// "Scene N" labels + a blue playhead — same vocabulary as
// app/runs/[id]/edit/_editor.
//
// The ~5s CSS loop tells one story: a cursor glides to a "Text size" stepper,
// the value ticks up then back down, and a heading in the faux canvas SCALES live
// in response — "edit your video's text, live." Pure CSS keyframes (transform/
// opacity only), no JS animation, no state. Everything is driven by a single
// shared 5s timeline so the cursor, the stepper value, the button "press" pulse,
// and the heading scale all stay in lockstep.
//
// Reduced motion: the whole animation is wrapped so `prefers-reduced-motion`
// freezes every keyframe at its rest frame (a clean, legible static editor).

import { Reveal } from './Motion'

export default function EditorDemo() {
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
            Every cut ships as structured, editable scenes — nudge the copy, retime a
            beat, or scale a headline live. No timeline wrangling, no re-render wait.
          </p>
        </Reveal>

        {/* The faux editor */}
        <Reveal className="mt-12">
          <div className="ed-demo mx-auto w-full max-w-3xl overflow-hidden rounded-2xl border border-[#D4E2FB] bg-white shadow-[0_30px_80px_-40px_rgba(30,58,120,0.32)] ring-1 ring-inset ring-[#EAF1FF]">
            {/* ---- top chrome bar ---- */}
            <div className="flex items-center gap-3 border-b border-[#E6EAF0] bg-white px-4 py-2.5">
              <span aria-hidden="true" className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#3B82F6]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#3B82F6]/30" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#3B82F6]/30" />
              </span>
              <span className="text-xs font-medium text-[#5A6472]">acme-launch.mp4</span>
              <span className="ml-auto rounded-md bg-[#3B82F6] px-2.5 py-1 text-[11px] font-semibold text-white">
                Export
              </span>
            </div>

            {/* ---- body: stage (left) + inspector (right) ---- */}
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_200px]">
              {/* dark video stage with the LIVE-scaling heading */}
              <div className="relative grid aspect-video place-items-center overflow-hidden bg-[#0B0F1A] px-6">
                {/* faint stage grid for depth */}
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 opacity-[0.10]"
                  style={{
                    backgroundImage:
                      'linear-gradient(#3B82F6 1px, transparent 1px), linear-gradient(90deg, #3B82F6 1px, transparent 1px)',
                    backgroundSize: '28px 28px',
                  }}
                />
                <div className="relative text-center">
                  <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.2em] text-[#60A5FA]">
                    Scene 2
                  </p>
                  {/* THIS heading scales live in response to the stepper */}
                  <h3 className="ed-demo__headline font-semibold leading-tight text-white">
                    Ship it today.
                  </h3>
                </div>
              </div>

              {/* inspector: the "Text size" stepper the cursor drives */}
              <div className="border-t border-[#E6EAF0] bg-[#F7F9FC] p-4 sm:border-l sm:border-t-0">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-[#5A6472]">
                  Inspector
                </p>
                <label className="mt-4 block text-xs font-medium text-[#0E1320]">
                  Text size
                </label>
                <div className="mt-1.5 flex items-center justify-between rounded-lg border border-[#D4E2FB] bg-white px-2 py-1.5">
                  <span aria-hidden="true" className="text-sm font-semibold text-[#9AA6B8]">
                    −
                  </span>
                  {/* the value display ticks 48 → 64 → 48 in lockstep with the loop */}
                  <span className="ed-demo__value tabular-nums text-sm font-semibold text-[#0E1320]">
                    48
                  </span>
                  {/* the "+" control the cursor presses — pulses on each press */}
                  <span
                    aria-hidden="true"
                    className="ed-demo__plus grid h-5 w-5 place-items-center rounded-md text-sm font-semibold text-[#2563EB]"
                  >
                    +
                  </span>
                </div>
                <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[#EEF1F6]">
                  <span className="ed-demo__bar block h-full rounded-full bg-[#3B82F6]" />
                </div>
              </div>
            </div>

            {/* ---- blue timeline with "Scene N" clips + playhead ---- */}
            <div className="relative border-t border-[#E6EAF0] bg-white px-4 py-3">
              <div className="relative flex h-9 gap-1.5">
                {[1, 2, 3, 4].map((n) => (
                  <div
                    key={n}
                    className={`grid flex-1 place-items-center rounded-md text-[11px] font-semibold text-white ${
                      n === 2 ? 'bg-[#3B82F6] ring-2 ring-[#2563EB]' : 'bg-[#3B82F6]/80'
                    }`}
                  >
                    Scene {n}
                  </div>
                ))}
                {/* live playhead sweeping the timeline */}
                <span
                  aria-hidden="true"
                  className="ed-demo__playhead absolute top-0 bottom-0 w-0.5 rounded bg-[#3B82F6]"
                  style={{ boxShadow: '0 0 8px 1px rgba(59,130,246,0.55)' }}
                />
              </div>
            </div>

            {/* ---- the animated cursor, gliding to the "+" control ---- */}
            <span aria-hidden="true" className="ed-demo__cursor">
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
        /* Shared 5s loop. Rest frame (reduced-motion) = the start of each
           keyframe set: heading at 48px, value "48", cursor parked, playhead left. */
        .ed-demo {
          position: relative;
        }

        /* Headline scales 48 → 64 → 48 (transform-only for GPU compositing). */
        .ed-demo__headline {
          font-size: 2.6rem; /* visual base; transform does the live scaling */
          transform-origin: center;
          animation: ed-headline 5s ease-in-out infinite;
        }
        @keyframes ed-headline {
          0%,
          18% {
            transform: scale(1);
          }
          42%,
          62% {
            transform: scale(1.33);
          }
          86%,
          100% {
            transform: scale(1);
          }
        }

        /* The numeric value crossfades 48 → 64 → 48 via a ::before overlay so the
           static text node ("48") stays as the reduced-motion rest frame. */
        .ed-demo__value {
          position: relative;
        }
        .ed-demo__value::before {
          content: '64';
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          opacity: 0;
          animation: ed-value 5s steps(1, end) infinite;
        }
        @keyframes ed-value {
          0%,
          40% {
            opacity: 0;
          }
          41%,
          63% {
            opacity: 1;
          }
          64%,
          100% {
            opacity: 0;
          }
        }
        /* Hide the underlying "48" while "64" shows, so they don't overlap. */
        .ed-demo__value {
          animation: ed-value-base 5s steps(1, end) infinite;
        }
        @keyframes ed-value-base {
          0%,
          40% {
            color: #0e1320;
          }
          41%,
          63% {
            color: transparent;
          }
          64%,
          100% {
            color: #0e1320;
          }
        }

        /* The size bar fills as the value rises. */
        .ed-demo__bar {
          width: 50%;
          animation: ed-bar 5s ease-in-out infinite;
        }
        @keyframes ed-bar {
          0%,
          18% {
            width: 50%;
          }
          42%,
          62% {
            width: 85%;
          }
          86%,
          100% {
            width: 50%;
          }
        }

        /* The "+" control pulses each time the cursor "presses" it. */
        .ed-demo__plus {
          animation: ed-plus 5s ease-out infinite;
        }
        @keyframes ed-plus {
          0%,
          24% {
            background: transparent;
            transform: scale(1);
          }
          28% {
            background: #dbeafe;
            transform: scale(0.86);
          }
          34% {
            background: transparent;
            transform: scale(1);
          }
          100% {
            background: transparent;
            transform: scale(1);
          }
        }

        /* Cursor glides from the stage to the "+" control, taps, then drifts back. */
        .ed-demo__cursor {
          position: absolute;
          top: 38%;
          left: 30%;
          z-index: 10;
          pointer-events: none;
          animation: ed-cursor 5s ease-in-out infinite;
        }
        @keyframes ed-cursor {
          0% {
            top: 40%;
            left: 30%;
            transform: scale(1);
          }
          22% {
            top: 58%;
            left: 86%;
            transform: scale(1);
          }
          27% {
            transform: scale(0.82);
          }
          32% {
            transform: scale(1);
          }
          62% {
            top: 58%;
            left: 86%;
          }
          100% {
            top: 40%;
            left: 30%;
          }
        }

        /* Playhead sweeps across the timeline, paused near Scene 2 during the edit. */
        .ed-demo__playhead {
          left: 6%;
          animation: ed-playhead 5s ease-in-out infinite;
        }
        @keyframes ed-playhead {
          0% {
            left: 6%;
          }
          18%,
          70% {
            left: 38%;
          }
          100% {
            left: 92%;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .ed-demo__headline,
          .ed-demo__value::before,
          .ed-demo__value,
          .ed-demo__bar,
          .ed-demo__plus,
          .ed-demo__cursor,
          .ed-demo__playhead {
            animation: none !important;
          }
          /* Freeze a clean static frame. */
          .ed-demo__headline {
            transform: scale(1);
          }
          .ed-demo__value::before {
            display: none;
          }
          .ed-demo__bar {
            width: 50%;
          }
          .ed-demo__cursor {
            top: 40%;
            left: 30%;
          }
          .ed-demo__playhead {
            left: 38%;
          }
        }
      `}</style>
    </section>
  )
}
