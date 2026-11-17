import './Loader.css'

// The same shield and tick as the Pramaan mark (BrandMark): proof, drawn stroke by stroke.
const SHIELD = 'M16 2.5l11 4v8.2c0 6.6-4.4 11.2-11 14.8C9.4 25.9 5 21.3 5 14.7V6.5z'
const TICK = 'M10.8 15.6l3.8 3.8 6.8-7.2'

/**
 * Pramaan's loader. The shield draws itself and the tick that proves it follows, then it starts
 * over, so a wait always reads as "being checked", never as a stuck page. Reduced motion shows the
 * finished mark. `label` is spoken to screen readers and shown under the mark.
 */
export default function Loader({ label = 'Loading', size = 56 }) {
  return (
    <div className="loader" role="status" aria-live="polite">
      <svg
        className="loader-mark"
        width={size}
        height={size}
        viewBox="0 0 32 32"
        aria-hidden="true"
      >
        <path className="loader-track" d={SHIELD} />
        <g className="loader-draw">
          <path className="loader-shield" d={SHIELD} pathLength="100" />
          <path className="loader-tick" d={TICK} pathLength="100" />
        </g>
      </svg>
      <span className="loader-label">{label}</span>
    </div>
  )
}
