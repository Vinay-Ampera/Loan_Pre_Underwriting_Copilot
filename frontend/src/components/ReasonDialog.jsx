import { useState } from 'react'
import Dialog from './Dialog'

export const MIN_REASON = 10

/**
 * The second click for a change that affects every new case: say why in your own words (at least
 * ten characters), then confirm. Nothing is sent until the confirm button is pressed. `blocked`
 * keeps the confirm button off until something else in the dialog is done (a tick, say).
 */
export default function ReasonDialog({
  title,
  confirmLabel,
  children,
  busy = false,
  error = null,
  blocked = false,
  onClose,
  onConfirm,
}) {
  const [reason, setReason] = useState('')
  const ok = reason.trim().length >= MIN_REASON
  return (
    <Dialog title={title} onClose={onClose} labelledBy="reason-dialog-title">
      {children}
      <div className="field">
        <label htmlFor="reason-text">Why are you making this change?</label>
        <textarea
          id="reason-text"
          className="input"
          rows={3}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          data-autofocus
        />
        <p className="small muted">
          At least {MIN_REASON} characters. It is kept with the change in the audit log.
        </p>
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
          className="btn btn-primary"
          disabled={!ok || busy || blocked}
          onClick={() => onConfirm(reason.trim())}
        >
          {busy ? 'Saving…' : confirmLabel}
        </button>
      </div>
    </Dialog>
  )
}
