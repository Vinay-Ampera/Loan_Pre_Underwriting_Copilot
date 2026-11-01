import './ScoreBadge.css'

/** Total score and band. "Not computed" when the run stopped (the UI never computes a score). */
export default function ScoreBadge({ score, band, indicative }) {
  const tone = band || 'none'
  return (
    <div className={`score-badge score-${tone}`}>
      <div
        className="score-num"
        aria-label={score == null ? 'Score not computed' : `Score ${score}`}
      >
        {score == null ? '–' : Number(score).toString()}
        {score != null && <span className="score-of"> / 100</span>}
      </div>
      <div className="score-band">{band ? band.toUpperCase() : 'NOT COMPUTED'}</div>
      {score == null && indicative != null && (
        <div className="small muted">Indicative only: {Number(indicative).toString()}</div>
      )}
    </div>
  )
}
