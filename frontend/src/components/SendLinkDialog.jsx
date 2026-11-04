import { useState } from 'react'
import { api } from '../api/client'
import Dialog from './Dialog'
import './MessageDialog.css'

/**
 * The "Upload link" message. It carries only the link and the usual fraud warning: no name,
 * score, status, missing item or reason. Step one prepares it (the server checks the content);
 * step two sends it and is the second click. The token stays in this dialog's memory only.
 */
export default function SendLinkDialog({ caseId, linkId, token, recipient = '', onClose }) {
  const [email, setEmail] = useState(recipient && !recipient.includes('*') ? recipient : '')
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(false)

  async function prepare() {
    setBusy(true)
    setError(null)
    try {
      const m = await api.post(`/cases/${caseId}/messages`, {
        template: 'upload_link',
        recipient_email: email.trim(),
        link_id: linkId,
        link_token: token,
      })
      if (m.status === 'blocked') setError(`Not sent: ${m.block_reason}.`)
      else setDraft(m)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function send() {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/messages/${draft.id}/send`, { second_click: true, link_token: token })
      setSent(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog title="Send the upload link" onClose={onClose} labelledBy="send-link-title">
      {sent ? (
        <>
          <p>The message was sent. You can find it under Sent items.</p>
          <div className="dialog-actions">
            <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
              Close
            </button>
          </div>
        </>
      ) : !draft ? (
        <>
          <div className="field">
            <label htmlFor="link-email">Customer email</label>
            <input
              id="link-email"
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
              data-autofocus
            />
          </div>
          <p className="small muted">
            The message holds only the link and the fraud warning. Nothing about the case goes in
            it.
          </p>
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
              disabled={busy || !email.includes('@')}
              onClick={prepare}
            >
              Prepare the message
            </button>
          </div>
        </>
      ) : (
        <>
          <p>This is exactly what the customer will receive:</p>
          <pre className="msg-final">{draft.text}</pre>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={onClose} data-autofocus>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={send}>
              Send to the customer
            </button>
          </div>
        </>
      )}
    </Dialog>
  )
}
