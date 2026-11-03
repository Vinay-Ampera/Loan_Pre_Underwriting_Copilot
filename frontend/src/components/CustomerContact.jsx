import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAsync } from '../hooks/useAsync'
import Dialog from './Dialog'
import MessageDialog from './MessageDialog'
import { MessageChip } from '../pages/SentItemsPage'
import './CustomerContact.css'

const UNSENT = ['draft', 'blocked']
const when = (m) =>
  new Date(m.sent_at || m.created_at).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

/**
 * Backing out of the dialog leaves an unsent draft. When one exists, "Write a message" asks first:
 * continue it, start a new one (keeping or deleting the old draft), or cancel. The delete button
 * is labelled as a delete and sits in this dialog, so it is the confirming second click.
 */
function DraftChoice({ draft, busy, error, onContinue, onNew, onDeleteAndNew, onClose }) {
  return (
    <Dialog title="You have an unsent draft" onClose={onClose} labelledBy="draft-choice-title">
      <p>
        A {draft.status === 'blocked' ? 'blocked message' : 'draft'} from {when(draft)} was not
        sent. Nothing has gone to the customer.
      </p>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions choice-actions">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="btn" onClick={onNew} disabled={busy}>
          Start a new message
        </button>
        <button type="button" className="btn btn-danger" onClick={onDeleteAndNew} disabled={busy}>
          Delete the draft and start new
        </button>
        <button type="button" className="btn btn-primary" onClick={onContinue} data-autofocus>
          Continue the draft
        </button>
      </div>
    </Dialog>
  )
}

/** After confirm, override or a stopped run: the officer may send the customer a contact request. */
export default function CustomerContact({ caseId, recipient }) {
  const { data, reload } = useAsync(() => api.get(`/cases/${caseId}/messages`), [caseId])
  const [mode, setMode] = useState(null) // 'choose' | 'write' | null
  const [existing, setExisting] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const messages = data || []
  const latestUnsent = messages.find((m) => UNSENT.includes(m.status)) || null

  function write(draft = null) {
    setExisting(draft)
    setMode('write')
  }
  async function deleteAndNew() {
    setBusy(true)
    setError(null)
    try {
      await api.del(`/messages/${latestUnsent.id}`)
      await reload()
      write(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }
  const close = () => {
    setMode(null)
    setExisting(null)
    setError(null)
  }

  return (
    <div className="card customer-contact">
      <div className="contact-head">
        <h3>Contact the customer</h3>
        <p className="small muted">
          Send a short request to get in touch. It never contains case details, a score or a result.
        </p>
      </div>
      <button
        type="button"
        className="btn contact-write"
        onClick={() => (latestUnsent ? setMode('choose') : write(null))}
      >
        Write a message
      </button>
      {messages.length > 0 && (
        <div className="contact-recent">
          <h4 className="contact-sub">Recent messages</h4>
          <ul className="contact-list" aria-label="Messages for this case">
            {messages.slice(0, 3).map((m) => (
              <li key={m.id}>
                <div className="contact-item">
                  <span className="contact-label">{m.template_label}</span>
                  <span className="small muted">{when(m)}</span>
                </div>
                <MessageChip status={m.status} />
              </li>
            ))}
          </ul>
          <Link to="/messages" className="small contact-all">
            See all in Sent items
          </Link>
        </div>
      )}
      {mode === 'choose' && (
        <DraftChoice
          draft={latestUnsent}
          busy={busy}
          error={error}
          onContinue={() => write(latestUnsent)}
          onNew={() => write(null)}
          onDeleteAndNew={deleteAndNew}
          onClose={close}
        />
      )}
      {mode === 'write' && (
        <MessageDialog
          caseId={caseId}
          recipient={recipient}
          existing={existing}
          onClose={close}
          onDone={reload}
        />
      )}
    </div>
  )
}
