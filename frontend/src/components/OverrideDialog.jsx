import { useState } from 'react'
import Dialog from './Dialog'
import './OverrideDialog.css'

export const MIN_REASON = 15
const DECISIONS = ['approve', 'refer', 'reject']
const WORD = { recommend_approve: 'approve', refer: 'refer', recommend_reject: 'reject' }

/** Override needs a different decision and a written reason; submit stays disabled without them. */
export default function OverrideDialog({
  recommendation,
  recommendationText,
  busy,
  error,
  onClose,
  onSubmit,
}) {
  const system = WORD[recommendation]
  const [decision, setDecision] = useState('')
  const [reason, setReason] = useState('')
  const trimmed = reason.trim()
  const valid = decision && decision !== system && trimmed.length >= MIN_REASON

  return (
    <Dialog title="Override the recommendation" onClose={onClose}>
      <p>
        The system recommended: <strong>{system}</strong>.{' '}
        <span className="muted">{recommendationText}.</span>
      </p>
      <div className="field">
        <label htmlFor="override-decision">Your decision</label>
        <select
          id="override-decision"
          className="select"
          value={decision}
          onChange={(e) => setDecision(e.target.value)}
          data-autofocus
        >
          <option value="">Choose…</option>
          {DECISIONS.filter((d) => d !== system).map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="override-reason">Reason (required)</label>
        <textarea
          id="override-reason"
          className="textarea"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-describedby="override-help"
          aria-invalid={reason.length > 0 && trimmed.length < MIN_REASON}
        />
        <span id="override-help" className="small muted">
          {trimmed.length < MIN_REASON
            ? `Write at least ${MIN_REASON} characters explaining why. ${trimmed.length}/${MIN_REASON}`
            : 'This reason is kept on the case and may be reviewed by an admin.'}
        </span>
      </div>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-danger"
          disabled={!valid || busy}
          onClick={() => onSubmit({ final_decision: decision, reason: trimmed })}
        >
          Submit override
        </button>
      </div>
    </Dialog>
  )
}
