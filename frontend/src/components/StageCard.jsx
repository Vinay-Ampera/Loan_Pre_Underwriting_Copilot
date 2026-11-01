import { useState } from 'react'
import FindingList from './FindingList'
import StatusChip from './StatusChip'
import './StageCard.css'

/** One scoring stage: name, score out of max, status, expandable findings with rule and clause. */
export default function StageCard({ row, findings, clauses, unverified }) {
  const [open, setOpen] = useState(findings.some((f) => f.severity === 'hard_fail'))
  const pct = row.ran && row.max ? Math.max(0, Math.min(100, (row.score / row.max) * 100)) : 0
  const stoppedHere = findings.some((f) => f.severity === 'hard_fail')
  const id = `stage-${row.stage}`
  return (
    <section className="stage-card card rise">
      <button
        type="button"
        className="stage-head"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="stage-name">{row.label}</span>
        <span className="stage-score">
          {row.ran ? `${Number(row.score)} / ${Number(row.max)}` : `not run / ${Number(row.max)}`}
        </span>
        {!row.ran ? (
          <StatusChip tone="stopped">Not run</StatusChip>
        ) : stoppedHere ? (
          <StatusChip tone="reject">Hard fail</StatusChip>
        ) : unverified ? (
          <StatusChip tone="unverified">Unverified</StatusChip>
        ) : findings.length ? (
          <StatusChip tone="refer">{findings.length} to review</StatusChip>
        ) : (
          <StatusChip tone="approve">Passed</StatusChip>
        )}
        <span className="stage-caret" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
      </button>
      <div className="stage-bar" aria-hidden="true">
        <div className="stage-fill" style={{ width: `${pct}%` }} />
      </div>
      {open && (
        <div id={id} className="stage-body">
          {unverified && (
            <p className="unverified-note">
              Could not be verified automatically. Please check manually.
            </p>
          )}
          {row.ran ? (
            <FindingList findings={findings} clauses={clauses} />
          ) : (
            <p className="muted">
              This stage was not run because an earlier stage stopped the case.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
