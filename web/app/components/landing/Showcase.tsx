// Showcase — example output cards (by format, not by client). Each card's 16:9
// "video poster" is a pure-SVG mock drawn inline (no screenshots, no raster, no
// brand names). Server component — fully static.

interface Example {
  /** unique suffix for SVG def ids so the three posters never collide */
  id: string
  label: string
  caption: string
}

const EXAMPLES: readonly Example[] = [
  {
    id: 'a',
    label: 'SaaS dashboard launch',
    caption: 'Promise → product reveal → proof → CTA.',
  },
  {
    id: 'b',
    label: 'AI feature reveal',
    caption: 'The old way, then the one-line magic.',
  },
  {
    id: 'c',
    label: 'Mobile app teaser',
    caption: 'Screens in motion, scored to a beat.',
  },
]

/** A play triangle inside a translucent circle, centered on the poster. */
function PlayBadge() {
  return (
    <g transform="translate(160 90)">
      <circle r="26" fill="#FFFFFF" fillOpacity="0.18" />
      <circle r="26" fill="none" stroke="#FFFFFF" strokeOpacity="0.55" strokeWidth="1.5" />
      <path d="M -7 -11 L 13 0 L -7 11 Z" fill="#FFFFFF" fillOpacity="0.95" />
    </g>
  )
}

/** Bottom-right duration chip reading 0:30. */
function DurationChip() {
  return (
    <g transform="translate(266 158)">
      <rect width="44" height="20" rx="6" fill="#14171C" fillOpacity="0.55" />
      <text
        x="22"
        y="14"
        textAnchor="middle"
        fontSize="11"
        fontWeight="600"
        fill="#FFFFFF"
        fillOpacity="0.92"
      >
        0:30
      </text>
    </g>
  )
}

/**
 * Poster A — a window/dashboard motif: a title bar with three dots over a soft
 * coral-to-ink gradient field.
 */
function PosterDashboard() {
  return (
    <svg viewBox="0 0 320 180" className="h-full w-full" aria-hidden="true">
      <defs>
        <linearGradient id="field-a" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#2563EB" />
          <stop offset="55%" stopColor="#1E3A8A" />
          <stop offset="100%" stopColor="#14171C" />
        </linearGradient>
        <clipPath id="clip-a">
          <rect width="320" height="180" rx="14" />
        </clipPath>
      </defs>
      <g clipPath="url(#clip-a)">
        <rect width="320" height="180" fill="url(#field-a)" />
        {/* window title bar */}
        <rect x="22" y="20" width="276" height="120" rx="9" fill="#FFFFFF" fillOpacity="0.10" />
        <rect x="22" y="20" width="276" height="24" rx="9" fill="#FFFFFF" fillOpacity="0.10" />
        <circle cx="36" cy="32" r="3" fill="#FFFFFF" fillOpacity="0.55" />
        <circle cx="48" cy="32" r="3" fill="#FFFFFF" fillOpacity="0.4" />
        <circle cx="60" cy="32" r="3" fill="#FFFFFF" fillOpacity="0.4" />
        {/* dashboard tiles */}
        <rect x="34" y="56" width="78" height="34" rx="6" fill="#FFFFFF" fillOpacity="0.16" />
        <rect x="120" y="56" width="78" height="34" rx="6" fill="#FFFFFF" fillOpacity="0.12" />
        <rect x="206" y="56" width="78" height="34" rx="6" fill="#FFFFFF" fillOpacity="0.12" />
        <rect x="34" y="100" width="160" height="28" rx="6" fill="#FFFFFF" fillOpacity="0.10" />
        <rect x="202" y="100" width="82" height="28" rx="6" fill="#FFFFFF" fillOpacity="0.16" />
        <PlayBadge />
        <DurationChip />
      </g>
    </svg>
  )
}

/**
 * Poster B — an AI feature motif: a rising chart line over a soft ink-to-coral
 * gradient field.
 */
function PosterChart() {
  return (
    <svg viewBox="0 0 320 180" className="h-full w-full" aria-hidden="true">
      <defs>
        <linearGradient id="field-b" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#14171C" />
          <stop offset="45%" stopColor="#16223F" />
          <stop offset="100%" stopColor="#2563EB" />
        </linearGradient>
        <linearGradient id="line-b" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0.95" />
        </linearGradient>
        <clipPath id="clip-b">
          <rect width="320" height="180" rx="14" />
        </clipPath>
      </defs>
      <g clipPath="url(#clip-b)">
        <rect width="320" height="180" fill="url(#field-b)" />
        {/* plot frame */}
        <rect x="30" y="28" width="260" height="108" rx="9" fill="#FFFFFF" fillOpacity="0.08" />
        {/* gridlines */}
        <line x1="30" y1="64" x2="290" y2="64" stroke="#FFFFFF" strokeOpacity="0.12" strokeWidth="1" />
        <line x1="30" y1="100" x2="290" y2="100" stroke="#FFFFFF" strokeOpacity="0.12" strokeWidth="1" />
        {/* area under the line */}
        <path
          d="M 44 122 L 96 104 L 148 110 L 200 74 L 252 50 L 276 42 L 276 130 L 44 130 Z"
          fill="#FFFFFF"
          fillOpacity="0.08"
        />
        {/* rising line */}
        <path
          d="M 44 122 L 96 104 L 148 110 L 200 74 L 252 50 L 276 42"
          fill="none"
          stroke="url(#line-b)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="276" cy="42" r="3.5" fill="#FFFFFF" />
        <PlayBadge />
        <DurationChip />
      </g>
    </svg>
  )
}

/**
 * Poster C — a mobile app motif: a phone frame with stacked content rows over a
 * soft coral diagonal gradient field.
 */
function PosterMobile() {
  return (
    <svg viewBox="0 0 320 180" className="h-full w-full" aria-hidden="true">
      <defs>
        <linearGradient id="field-c" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#3B82F6" />
          <stop offset="50%" stopColor="#2563EB" />
          <stop offset="100%" stopColor="#1C2026" />
        </linearGradient>
        <clipPath id="clip-c">
          <rect width="320" height="180" rx="14" />
        </clipPath>
      </defs>
      <g clipPath="url(#clip-c)">
        <rect width="320" height="180" fill="url(#field-c)" />
        {/* phone frame, centered */}
        <rect x="129" y="26" width="62" height="128" rx="12" fill="#FFFFFF" fillOpacity="0.14" />
        <rect x="135" y="34" width="50" height="112" rx="7" fill="#FFFFFF" fillOpacity="0.10" />
        {/* notch */}
        <rect x="150" y="38" width="20" height="4" rx="2" fill="#FFFFFF" fillOpacity="0.5" />
        {/* content rows */}
        <rect x="141" y="50" width="38" height="22" rx="4" fill="#FFFFFF" fillOpacity="0.22" />
        <rect x="141" y="78" width="38" height="6" rx="3" fill="#FFFFFF" fillOpacity="0.3" />
        <rect x="141" y="90" width="26" height="6" rx="3" fill="#FFFFFF" fillOpacity="0.22" />
        <rect x="141" y="106" width="38" height="6" rx="3" fill="#FFFFFF" fillOpacity="0.3" />
        <rect x="141" y="118" width="30" height="6" rx="3" fill="#FFFFFF" fillOpacity="0.22" />
        {/* floating side screens for "screens in motion" */}
        <rect x="86" y="58" width="34" height="64" rx="8" fill="#FFFFFF" fillOpacity="0.08" />
        <rect x="200" y="58" width="34" height="64" rx="8" fill="#FFFFFF" fillOpacity="0.08" />
        <PlayBadge />
        <DurationChip />
      </g>
    </svg>
  )
}

function Poster({ id }: { id: string }) {
  if (id === 'a') return <PosterDashboard />
  if (id === 'b') return <PosterChart />
  return <PosterMobile />
}

export default function Showcase() {
  return (
    <section id="examples" className="bg-[#F7F8FA] px-5 py-20 sm:py-24">
      <div className="mx-auto max-w-5xl">
        {/* Section header */}
        <div className="mx-auto max-w-xl text-center">
          <span className="inline-block rounded-full border border-amber/20 bg-amber/5 px-3 py-1 text-xs font-medium text-amber">
            Example outputs
          </span>
          <h2 className="mt-4 text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            What comes out the other side.
          </h2>
          <p className="mx-auto mt-3 text-slate-500">
            Finished, editable launch videos — generated from a single URL.
          </p>
        </div>

        {/* Example cards */}
        <div className="mt-12 grid gap-6 sm:grid-cols-3">
          {EXAMPLES.map((ex) => (
            <figure
              key={ex.id}
              className="overflow-hidden rounded-2xl border border-black/5 bg-white shadow-[0_18px_50px_-20px_rgba(20,23,28,0.25)] transition hover:border-black/10 hover:shadow-sm"
            >
              <div className="aspect-video w-full">
                <Poster id={ex.id} />
              </div>
              <figcaption className="p-5">
                <p className="font-semibold text-ink">{ex.label}</p>
                <p className="mt-1 text-sm text-slate-500">{ex.caption}</p>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  )
}
