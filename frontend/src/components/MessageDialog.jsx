import { useEffect, useState } from 'react'
import { api } from '../api/client'
import Callout from './Callout'
import Dialog from './Dialog'
import { Skeleton } from './States'
import './MessageDialog.css'

const EMAIL = /^[^@\s*]+@[^@\s]+\.[^@\s]+$/

/**
 * Draft a short contact request to the customer. Step 1 edits the text; "Review" saves a draft and
 * the server checks it. Step 2 shows the final text exactly as it will be sent, and only the button
 * there sends it (the second click). The footer and contact lines are locked: the server adds them.
 */
export default function MessageDialog({ caseId, recipient, existing, onClose, onDone }) {
  const [meta, setMeta] = useState(null)
  const [template, setTemplate] = useState(existing?.template || 'general_contact')
  const [body, setBody] = useState(existing?.body ?? null)
  const [includeRef, setIncludeRef] = useState(existing?.case_ref_included ?? false)
  const [email, setEmail] = useState('')
  const [draft, setDraft] = useState(existing && existing.status !== 'sent' ? existing : null)
  const [step, setStep] = useState('edit')
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sent, setSent] = useState(false)

  const loadMeta = () =>
    api
      .get('/messages/templates')
      .then(setMeta)
      .catch((e) => setError(e.message))
  useEffect(() => {
    loadMeta()
  }, [])

  const chosen = meta?.templates.find((t) => t.code === template)
  const text = body ?? chosen?.body ?? ''
  const needsEmail = !recipient && !existing
  const emailOk = !needsEmail || EMAIL.test(email.trim())

  function pick(code) {
    setTemplate(code)
    setBody(null)
    setDraft(null) // another template is a new message
  }

  async function review() {
    setBusy(true)
    setError(null)
    try {
      const payload = {
        body: text,
        include_case_ref: includeRef,
        recipient_email: email.trim() || null,
      }
      const res = draft
        ? await api.put(`/messages/${draft.id}`, {
            ...payload,
            recipient_email: payload.recipient_email,
          })
        : await api.post(`/cases/${caseId}/messages`, { ...payload, template })
      setDraft(res)
      if (res.status === 'blocked') setError(null)
      else setStep('confirm')
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
      await api.post(`/messages/${draft.id}/send`, { second_click: true })
      setSent(true)
      onDone?.()
    } catch (e) {
      setError(e.message)
      onDone?.()
    } finally {
      setBusy(false)
    }
  }

  async function savePhone() {
    setError(null)
    try {
      await api.put('/profile/phone', { phone })
      setPhone('')
      await loadMeta()
    } catch (e) {
      setError(e.message)
    }
  }

  // Leaving with a saved draft: tell the caller so its list shows the draft that was left behind.
  function leave() {
    if (draft) onDone?.()
    onClose()
  }

  const blocked = draft?.status === 'blocked' ? draft.block_reason.split('; ') : []

  if (sent) {
    return (
      <Dialog title="Message sent" onClose={onClose} labelledBy="msg-title">
        <p>
          The message was sent to <strong>{draft.recipient}</strong> and is listed in Sent items. In
          this version it is printed in the backend terminal.
        </p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-primary" onClick={onClose} data-autofocus>
            Close
          </button>
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog
      title={step === 'edit' ? 'Contact the customer' : 'Send this message?'}
      onClose={leave}
      labelledBy="msg-title"
    >
      {!meta ? (
        error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : (
          <Skeleton lines={4} />
        )
      ) : step === 'edit' ? (
        <div className="msg-form">
          <Callout tone="warn" title="Keep it free of case details">
            Do not write a name, number, amount, score, result, missing item or reason. The message
            only asks the customer to contact you. A check blocks anything else.
          </Callout>
          <div className="field">
            <label htmlFor="msg-template">Template</label>
            <select
              id="msg-template"
              className="select"
              value={template}
              onChange={(e) => pick(e.target.value)}
              data-autofocus
              disabled={Boolean(existing)}
            >
              {meta.templates.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="msg-to">To</label>
            {needsEmail ? (
              <input
                id="msg-to"
                className="input"
                type="email"
                placeholder="Customer email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            ) : (
              <input
                id="msg-to"
                className="input"
                value={existing?.recipient || recipient}
                disabled
                readOnly
              />
            )}
            {needsEmail && (
              <span className="small muted">This case has no customer email. Enter one.</span>
            )}
          </div>
          <div className="field">
            <label htmlFor="msg-subject">Subject</label>
            <input id="msg-subject" className="input" value={meta.subject} disabled readOnly />
          </div>
          <div className="field">
            <label htmlFor="msg-body">Message</label>
            <textarea
              id="msg-body"
              className="textarea"
              rows={5}
              maxLength={meta.max_body}
              value={text}
              onChange={(e) => {
                setBody(e.target.value)
                setError(null)
              }}
              aria-describedby="msg-count"
            />
            <span id="msg-count" className="small muted">
              {text.length}/{meta.max_body}
            </span>
          </div>
          <label className="msg-check">
            <input
              type="checkbox"
              checked={includeRef}
              onChange={(e) => setIncludeRef(e.target.checked)}
            />{' '}
            Include the case reference
          </label>
          <div className="msg-locked" aria-label="Added automatically">
            <p className="small muted">Added automatically and cannot be edited:</p>
            {meta.contact.map((l) => (
              <p key={l}>{l}</p>
            ))}
            <p className="msg-footer">{meta.footer}</p>
            {!meta.phone_set && (
              <div className="msg-phone">
                <label htmlFor="msg-phone" className="small">
                  Your mobile number (optional, shown in the message)
                </label>
                <div className="msg-phone-row">
                  <input
                    id="msg-phone"
                    className="input mono"
                    inputMode="numeric"
                    maxLength={10}
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn"
                    disabled={!/^[6-9][0-9]{9}$/.test(phone)}
                    onClick={savePhone}
                  >
                    Save number
                  </button>
                </div>
              </div>
            )}
          </div>
          {blocked.length > 0 && (
            <div className="msg-blocked" role="alert">
              <strong>This message cannot be sent:</strong>
              <ul>
                {blocked.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <span className="small">Change the text and choose Review again.</span>
            </div>
          )}
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={leave}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !text.trim() || !emailOk}
              onClick={review}
            >
              Review
            </button>
          </div>
        </div>
      ) : (
        <div className="msg-form">
          <p className="small muted">
            To <strong>{draft.recipient}</strong> · Subject: {draft.subject}
          </p>
          <pre className="msg-final" data-testid="final-text">
            {draft.text}
          </pre>
          <p className="small muted">
            This is exactly what the customer will receive. Sending cannot be undone.
          </p>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="btn" onClick={() => setStep('edit')}>
              Back to edit
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={send}
              data-autofocus
            >
              Yes, send
            </button>
          </div>
        </div>
      )}
    </Dialog>
  )
}
