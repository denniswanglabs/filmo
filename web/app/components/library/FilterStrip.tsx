'use client'
// ── THE STRIP: NARROWING A LIBRARY THAT HAS GROWN ───────────────────────────
// Both libraries have the same problem past a few dozen rows, and it is not
// storage — it is FINDING. Thirteen filmos of one brand all reading "Updated
// today" is an unfindable library however well each row renders, and an assets
// page that mixes page captures, brand marks, recordings, stills and finished
// films in one wall is the same failure with more colours in it.
//
// So both pages get this, and it is one component rather than two so they
// cannot drift into different affordances for the same act.
//
// TWO THINGS IT DOES ON PURPOSE.
//
// 1. EVERY OPTION CARRIES ITS COUNT. A filter that might return nothing is a
//    guess the reader has to spend a click to check. With the count on the
//    control, the strip doubles as a census of the library.
//
// 2. THE ACTIVE OPTION EXPLAINS ITSELF. `hint` is what the type IS — "Pages
//    Filmo read", "Real screen footage" — carried over from the first version
//    of /assets, where it made the library double as an explanation of what the
//    agent actually collects. That is worth more than the row of pills it costs.
//
// Options that would return nothing are not rendered at all — the CALLER
// decides which exist, because only the caller knows what it read. Offering a
// filter that yields an empty list is offering a dead end.

export interface FilterOption<K extends string> {
  key: K
  label: string
  /** What this kind IS, in the reader's words. Shown under the strip while the
   *  option is active. Omit when the label already says everything. */
  hint?: string
  count: number
}

export default function FilterStrip<K extends string>({
  options, value, onChange, ariaLabel,
}: {
  options: FilterOption<K>[]
  value: K
  onChange: (k: K) => void
  ariaLabel: string
}) {
  const active = options.find((o) => o.key === value)

  return (
    <div className="libfilter">
      {/* Buttons with aria-pressed, not tabs: nothing here is a tabpanel, and
          calling it a tablist would promise a keyboard contract (arrow-key
          roving focus) that this does not implement. */}
      <div className="libfilter-row" role="group" aria-label={ariaLabel}>
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            className={'libfilter-pill' + (o.key === value ? ' on' : '')}
            aria-pressed={o.key === value}
            onClick={() => onChange(o.key)}
          >
            <span className="libfilter-label">{o.label}</span>
            <span className="libfilter-count">{o.count.toLocaleString()}</span>
          </button>
        ))}
      </div>
      {active?.hint ? <p className="libfilter-hint">{active.hint}</p> : null}

      <style>{`
        .libfilter { margin:0 0 18px; }
        /* At 390px the strip scrolls INSIDE ITSELF. The one thing it must never
           do is widen the page: a body that scrolls sideways on a phone is the
           bug, not the row of pills. */
        .libfilter-row { display:flex; gap:8px; overflow-x:auto;
          padding-bottom:2px; scrollbar-width:thin; }
        .libfilter-pill { flex:0 0 auto; display:inline-flex; align-items:center;
          gap:8px; background:#fff; border:1px solid #E6E6E3; border-radius:99px;
          padding:7px 14px; font:13px/1 Inter,-apple-system,sans-serif;
          color:#6E6E6A; cursor:pointer; white-space:nowrap;
          transition:background-color .15s, border-color .15s, color .15s; }
        .libfilter-pill:hover { border-color:#C9C9C4; color:#1B1B1A; }
        .libfilter-pill:focus-visible { outline:2px solid #3B82F6;
          outline-offset:3px; }
        /* The lit state is a filled chip, not a tint: at a glance the strip has
           to answer "what am I looking at" from across the room. */
        .libfilter-pill.on { background:#1B1B1A; border-color:#1B1B1A; color:#fff; }
        .libfilter-label { font-weight:500; }
        .libfilter-count { font-size:11.5px; color:#B6B6B2;
          font-variant-numeric:tabular-nums; }
        .libfilter-pill.on .libfilter-count { color:rgba(255,255,255,.62); }
        .libfilter-hint { margin:9px 0 0; font-size:12.5px; color:#8A8A86; }
        @media (prefers-reduced-motion:reduce) {
          .libfilter-pill { transition:none; } }
      `}</style>
    </div>
  )
}
