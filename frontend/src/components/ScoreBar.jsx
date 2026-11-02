import StatusChip from './StatusChip'
import './ScoreBar.css'

// The locked scoring decision (rules file). Shown as facts; nothing is computed here.
const WEIGHTS = [
  ['KYC', 20],
  ['Documents', 15],
  ['Income and FOIR', 30],
  ['Credit and behaviour', 25],
  ['Policy fit', 10],
]

/** The 100-point score as a proportional bar, then the three bands as a scale from 0 to 100. */
export default function ScoreBar() {
  return (
    <div className="scorebar2">
      <ul className="weights" aria-label="Score weights">
        {WEIGHTS.map(([name, pts], i) => (
          <li key={name} style={{ flexGrow: pts, '--tint': 100 - i * 14 }}>
            <span className="w-pts">{pts}</span>
            <span className="w-name">{name}</span>
          </li>
        ))}
      </ul>
      <div className="bandscale" aria-hidden="true">
        <span className="zone zone-reject" style={{ flexGrow: 60 }}>
          0 to 59
        </span>
        <span className="zone zone-refer" style={{ flexGrow: 25 }}>
          60 to 84
        </span>
        <span className="zone zone-approve" style={{ flexGrow: 15 }}>
          85+
        </span>
      </div>
      <ul className="bands2" aria-label="Score bands">
        <li>
          <StatusChip tone="approve">85 and above: recommend approve</StatusChip>
        </li>
        <li>
          <StatusChip tone="refer">60 to 84: refer</StatusChip>
        </li>
        <li>
          <StatusChip tone="reject">Below 60: recommend reject</StatusChip>
        </li>
      </ul>
    </div>
  )
}
