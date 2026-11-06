import { useState } from 'react'
import { api } from '../api/client'
import ConfirmDialog from './ConfirmDialog'
import Dialog from './Dialog'
import SendLinkDialog from './SendLinkDialog'

/** The address the applicant opens: this site's own origin plus the link path (`/u#token`). */
export const linkUrl = (path) => `${window.location.origin}${path}`

/**
 * "Ask the applicant": a link for this case that takes files only. Creating it is an outward
 * action, so it needs the second click. The address is shown once (only its hash is kept), with
 * a copy button and a way to send it as the Stage 9 "Upload link" message.
 */
export default function AskApplicantDialog({ caseId, recipient, onClose, onDone }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [made, setMade] = useState(null)
  const [copied, setCopied] = useState(false)
  const [sending, setSending] = useState(false)

  async function create() {
    setBusy(true)
    setError(null)
    try {
      setMade(await api.post(`/cases/${caseId}/ask-applicant`, { second_click: true }))
      onDone?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(linkUrl(made.path))
      setCopied(true)
    } catch {
      setError('Copying did not work. Select the address and copy it by hand.')
    }
  }

  if (!made) {
    return (
      <ConfirmDialog
        title="Ask the applicant for the rest?"
        confirmLabel="Create the link"
        danger={false}
        busy={busy}
        error={error}
        onClose={onClose}
        onConfirm={create}
      >
        <p>
          This makes a secure upload link for this case. It stays open for a limited time, takes
          files only, and shows the applicant what is still needed. You will see the address once.
          Nothing is sent until you choose to send it.
        </p>
      </ConfirmDialog>
    )
  }
  if (sending) {
    return (
      <SendLinkDialog
        caseId={caseId}
        linkId={made.link_id}
        token={new URL(linkUrl(made.path)).hash.slice(1)}
        recipient={recipient}
        onClose={onClose}
      />
    )
  }
  return (
    <Dialog title="The applicant's link" onClose={onClose} labelledBy="ask-link-title">
      {made.token ? (
        <>
          <p>
            Copy this address. You can copy it again later from the Upload links page.
          </p>
          <input
            className="input mono"
            readOnly
            aria-label="Upload link address"
            value={linkUrl(made.path)}
            onFocus={(e) => e.target.select()}
          />
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={copy} data-autofocus>
              {copied ? 'Copied' : 'Copy the link'}
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setSending(true)}>
              Send it as a message
            </button>
            <button type="button" className="btn" onClick={onClose}>
              Done
            </button>
          </div>
        </>
      ) : (
        <>
          <p>
            The applicant&apos;s link for this case is still open, and it has been extended. Its
            address cannot be shown here. Open the Upload links page to copy it or to make a new
            address.
          </p>
          <div className="dialog-actions">
            <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
              Close
            </button>
          </div>
        </>
      )}
    </Dialog>
  )
}
