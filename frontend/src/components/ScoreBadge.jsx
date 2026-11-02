import './ScoreBadge.css'

const R = 52
const C = 2 * Math.PI * R

/** Score ring and band. "Not computed" when the run stopped (the UI never computes a score). */
export default function ScoreBadge({ score, band, indicative }) {
  const tone = band || 'none'
  const pct = score == null ? 0 : Math.max(0, Math.min(100, Number(score)))
  return (
    <div className={`score-badge score-${tone}`}>
      <div className="score-ring">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle className="ring-track" cx="60" cy="60" r={R} />
          <circle
            className="ring-fill"
            cx="60"
            cy="60"
            r={R}
            strokeDasharray={C}
            strokeDashoffset={C * (1 - pct / 100)}
            style={{ '--ring-from': C }}
          />
        </svg>
        <div
          className="score-num"
          aria-label={score == null ? 'Score not computed' : `Score ${score}`}
        >
          {score == null ? '–' : Number(score).toString()}
          {score != null && <span className="score-of">of 100</span>}
        </div>
      </div>
      <div className="score-band">{band ? band.toUpperCase() : 'NOT COMPUTED'}</div>
      {score == null && indicative != null && (
        <div className="small">Indicative only: {Number(indicative).toString()}</div>
      )}
    </div>
  )
}
