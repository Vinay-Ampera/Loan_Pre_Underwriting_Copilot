import './BrandMark.css'

/** The Pramaan mark and name. "Pramaan" means proof: a tick inside a shield. */
export default function BrandMark({ compact = false, inverse = false }) {
  return (
    <span className={`brand-lockup${inverse ? ' inverse' : ''}`}>
      <svg className="brand-glyph" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
        <path
          d="M16 2.5l11 4v8.2c0 6.6-4.4 11.2-11 14.8C9.4 25.900 5 21.300 5 14.700V6.500z"
          fill="currentColor"
        />
        <path
          d="M10.800 15.600l3.800 3.800 6.800-7.200"
          fill="none"
          stroke="var(--glyph-tick)"
          strokeWidth="2.600"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {!compact && <span className="brand-name">Pramaan</span>}
      {compact && <span className="sr-only">Pramaan</span>}
    </span>
  )
}
