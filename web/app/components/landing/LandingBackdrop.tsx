/** Shared Filmo mark-up for page backdrop + hero decoration. */
export function FilmoBrandMarks({ className = '' }: { className?: string }) {
  return (
    <div aria-hidden className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}>
      <div className="filmo-backdrop__wash absolute inset-0" />
      <svg
        viewBox="14 13 56 56"
        className="filmo-backdrop__blob absolute -right-[6%] top-[6%] h-[min(38vw,24rem)] w-[min(38vw,24rem)] text-[#3B82F6]"
        aria-hidden
      >
        <path
          fill="currentColor"
          fillRule="evenodd"
          d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
        />
      </svg>
      <svg
        viewBox="14 13 56 56"
        className="filmo-backdrop__blob absolute -bottom-[4%] -left-[8%] h-[min(32vw,20rem)] w-[min(32vw,20rem)] text-[#3B82F6]"
        aria-hidden
      >
        <path
          fill="currentColor"
          fillRule="evenodd"
          d="M42 17 C56 15 67 27 65 41 C63 55 52 67 38 65 C25 63 16 51 19 37 C21 25 30 19 42 17 Z M47 28.5 A8.5 8.5 0 1 1 47 45.5 A8.5 8.5 0 1 1 47 28.5 Z"
        />
      </svg>
    </div>
  )
}

/** Fixed decorative Filmo branding behind the landing page. */
export default function LandingBackdrop() {
  return (
    <div aria-hidden className="filmo-backdrop pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <FilmoBrandMarks />
    </div>
  )
}

/** Visible hero-layer branding (sits under headline, above stage aura). */
export function HeroBrandLayer() {
  return <FilmoBrandMarks className="filmo-hero-brand z-0" />
}
