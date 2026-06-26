// Sponsor credit for the Hermes Hackathon (Nous Research × NVIDIA × Stripe).
// Plain <img> (not next/image) — the marks are tiny static SVGs in /public and
// next/image blocks SVG sources unless dangerouslyAllowSVG is configured.
// A tasteful "Powered by" logo row — clean SVG marks + small labels, on-brand
// (white + light-blue). Reused on the landing (under the composer) and, in a
// compact variant, in the site footer so the credit appears app-wide.

type Credit = { src: string; label: string; sub: string; alt: string }

const CREDITS: Credit[] = [
  {
    src: '/brands/hermes.svg',
    label: 'Hermes',
    sub: 'Nous Research',
    alt: 'Hermes by Nous Research',
  },
  {
    src: '/brands/nvidia.svg',
    label: 'NVIDIA',
    sub: 'Nemotron',
    alt: 'NVIDIA Nemotron',
  },
  {
    src: '/brands/stripe.svg',
    label: 'Stripe',
    sub: 'Payments',
    alt: 'Stripe',
  },
]

/**
 * Sponsor credit. `compact` renders the footer variant: smaller, single-line
 * labels, no surrounding card.
 */
export default function PoweredBy({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">
          Powered by
        </span>
        {CREDITS.map((c) => (
          <span key={c.label} className="inline-flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={c.src}
              alt={c.alt}
              width={18}
              height={18}
              className="h-[18px] w-[18px] shrink-0 object-contain opacity-80"
            />
            <span className="text-xs text-[#5A6472]">
              {c.label}
              <span className="text-[#9AA6B8]"> · {c.sub}</span>
            </span>
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-[#D4E2FB] bg-white/70 px-6 py-5 ring-1 ring-inset ring-[#EAF1FF]">
      <p className="mb-4 text-center text-xs font-medium uppercase tracking-[0.14em] text-[#8A94A6]">
        Powered by
      </p>
      <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-5">
        {CREDITS.map((c) => (
          <div key={c.label} className="inline-flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={c.src}
              alt={c.alt}
              width={26}
              height={26}
              className="h-[26px] w-[26px] shrink-0 object-contain"
            />
            <span className="leading-tight">
              <span className="block text-sm font-semibold text-[#0E1320]">{c.label}</span>
              <span className="block text-xs text-[#5A6472]">{c.sub}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
