import { useState } from 'react'
import Dialog from './Dialog'
import StatusChip from './StatusChip'
import { loanLabel } from './LoanTypePicker'
import './PrecedentReviewCard.css'

const TONE = {
  pending: 'refer',
  approved: 'approve',
  rejected: 'reject',
  held: 'stopped',
  expired: 'stopped',
}

/** Original case summary, the officer's reason, similar precedents, then Approve or Reject. */
export default function PrecedentReviewCard({ p, onApprove, onReject }) {
  const maxDate = p.max_valid_until
  const [dialog, setDialog] = useState(null)
  const [until, setUntil] = useState(maxDate)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run(fn) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      setDialog(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="prec card rise">
      <header className="prec-head">
        <div>
          <h3>
            <span className="mono">{p.case_no}</span> · {loanLabel(p.loan_type)}
          </h3>
          <p className="small muted">
            Proposed by {p.proposed_by} on {new Date(p.created_at).toLocaleDateString()}
          </p>
        </div>
        <StatusChip tone={TONE[p.status]}>{p.status}</StatusChip>
      </header>
      <dl className="prec-grid">
        <div>
          <dt>System recommended</dt>
          <dd>
            {p.original_recommendation}
            {p.original_score != null && <span className="muted"> (score {p.original_score})</span>}
          </dd>
        </div>
        <div>
          <dt>Officer decided</dt>
          <dd>{p.final_decision}</dd>
        </div>
        <div className="wide">
          <dt>Officer&apos;s reason</dt>
          <dd>{p.officer_reason}</dd>
        </div>
        <div className="wide">
          <dt>Case summary</dt>
          <dd>{p.report_summary}</dd>
        </div>
        <div className="wide">
          <dt>Rules involved</dt>
          <dd>
            {p.rule_ids.map((r) => (
              <code key={r} className="rule-pill">
                {r}
              </code>
            ))}
          </dd>
        </div>
      </dl>
      <section>
        <h4>Similar approved precedents</h4>
        {p.similar.length === 0 ? (
          <p className="muted small">None share these rules yet.</p>
        ) : (
          <ul>
            {p.similar.map((s) => (
              <li key={s.id} className="small">
                {s.summary}{' '}
                <span className="muted">
                  → {s.final_decision}, until {s.valid_until}, {s.shared_rules} shared rule(s)
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {p.status === 'pending' && (
        <div className="prec-actions">
          <button type="button" className="btn" onClick={() => setDialog('reject')}>
            Reject
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setDialog('approve')}>
            Approve…
          </button>
        </div>
      )}
      {p.status === 'approved' && (
        <p className="small muted">
          Approved by {p.reviewed_by}; valid until {p.valid_until}.
        </p>
      )}

      {dialog === 'approve' && (
        <Dialog title="Approve this precedent?" onClose={() => setDialog(null)}>
          <p>
            Approved precedents are used only for borderline cases of the same loan type, never over
            a hard rule, and expire on the date below.
          </p>
          <div className="field">
            <label htmlFor={`until-${p.id}`}>Valid until</label>
            <input
              id={`until-${p.id}`}
              className="input"
              type="date"
              value={until}
              max={maxDate}
              onChange={(e) => setUntil(e.target.value)}
              data-autofocus
            />
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setDialog(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !until}
              onClick={() => run(() => onApprove(p.id, until))}
            >
              Yes, approve precedent
            </button>
          </div>
        </Dialog>
      )}
      {dialog === 'reject' && (
        <Dialog title="Reject this precedent?" onClose={() => setDialog(null)}>
          <p>It will not be used for any future case.</p>
          <div className="field">
            <label htmlFor={`note-${p.id}`}>Note (optional)</label>
            <textarea
              id={`note-${p.id}`}
              className="textarea"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              data-autofocus
            />
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setDialog(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy}
              onClick={() => run(() => onReject(p.id, note))}
            >
              Yes, reject precedent
            </button>
          </div>
        </Dialog>
      )}
    </article>
  )
}
