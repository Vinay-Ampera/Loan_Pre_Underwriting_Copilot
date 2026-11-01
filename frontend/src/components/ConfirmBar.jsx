import { useState } from 'react'
import Dialog from './Dialog'
import OverrideDialog from './OverrideDialog'
import './ConfirmBar.css'

const WORD = { recommend_approve: 'approve', refer: 'refer', recommend_reject: 'reject' }

/**
 * "Confirm recommendation" and "Override". Each opens a second dialog; nothing is recorded until
 * the button inside that dialog is pressed (second click). The server enforces the same rules.
 */
export default function ConfirmBar({ recommendation, recommendationText, onConfirm, onOverride }) {
  const [dialog, setDialog] = useState(null) // 'confirm' | 'override' | null
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const word = WORD[recommendation] || recommendation

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
    <div className="confirm-bar">
      <p className="confirm-note">A loan officer confirms every case, whatever the score.</p>
      <button type="button" className="btn btn-primary" onClick={() => setDialog('confirm')}>
        Confirm recommendation
      </button>
      <button type="button" className="btn" onClick={() => setDialog('override')}>
        Override
      </button>

      {dialog === 'confirm' && (
        <Dialog title="Confirm the recommendation?" onClose={() => setDialog(null)}>
          <p>{recommendationText}.</p>
          <p>
            You are confirming the system&apos;s recommendation to <strong>{word}</strong> this
            application. Your name and the time are recorded on the case.
          </p>
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
              data-autofocus
              disabled={busy}
              onClick={() => run(onConfirm)}
            >
              Yes, confirm
            </button>
          </div>
        </Dialog>
      )}
      {dialog === 'override' && (
        <OverrideDialog
          recommendation={recommendation}
          recommendationText={recommendationText}
          busy={busy}
          error={error}
          onClose={() => setDialog(null)}
          onSubmit={(payload) => run(() => onOverride(payload))}
        />
      )}
    </div>
  )
}
