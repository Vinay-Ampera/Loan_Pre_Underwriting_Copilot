import { useState } from 'react'
import './FindingList.css'

const SEVERITY = {
  hard_fail: { icon: '✕', label: 'Hard fail', cls: 'sev-hard' },
  cap: { icon: '!', label: 'Caps the band', cls: 'sev-cap' },
  points_lost: { icon: '−', label: 'Points lost', cls: 'sev-points' },
  note: { icon: 'i', label: 'Note', cls: 'sev-note' },
}
const ROLE = { primary: 'Applicant', co: 'Co-applicant' }

function Finding({ f, clauses }) {
  const [open, setOpen] = useState(false)
  const sev = SEVERITY[f.severity] || SEVERITY.note
  const clause = clauses.find((c) => c.clause_id === f.clause_id)
  return (
    <li className={`finding ${sev.cls}`}>
      <span className="finding-icon" aria-hidden="true">
        {sev.icon}
      </span>
      <div className="finding-body">
        <p>
          <span className="finding-sev">{sev.label}.</span> {f.message}
          {f.role && <span className="finding-role"> {ROLE[f.role]}</span>}
        </p>
        {f.explanation && <p className="muted">{f.explanation}</p>}
        <p className="finding-ids small">
          {f.rule_id && <code>{f.rule_id}</code>}
          {f.points_lost > 0 && <span className="muted"> −{f.points_lost} pts</span>}
          {f.clause_id && (
            <button
              type="button"
              className="clause-link"
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
            >
              <code>{f.clause_id}</code>
            </button>
          )}
        </p>
        {open && (
          <blockquote className="clause-text">
            {clause ? clause.text : 'The clause text is not part of this report.'}
          </blockquote>
        )}
        {f.evidence && Object.keys(f.evidence).length > 0 && (
          <details className="evidence">
            <summary>Evidence</summary>
            <dl>
              {Object.entries(f.evidence)
                .filter(([, v]) => v !== null && typeof v !== 'object')
                .map(([k, v]) => (
                  <div key={k}>
                    <dt>{k.replaceAll('_', ' ')}</dt>
                    <dd>{String(v)}</dd>
                  </div>
                ))}
            </dl>
          </details>
        )}
      </div>
    </li>
  )
}

export default function FindingList({ findings, clauses = [] }) {
  if (!findings.length) return <p className="muted">No findings.</p>
  return (
    <ul className="finding-list">
      {findings.map((f, i) => (
        <Finding key={`${f.rule_id}-${i}`} f={f} clauses={clauses} />
      ))}
    </ul>
  )
}
